import os
import sys
import json
import math
import shutil
import hashlib
import subprocess
import secrets
import uuid
import tempfile
import atexit
import logging
from datetime import datetime, timedelta, timezone
from flask import (
    Flask, render_template, request, jsonify,
    Response, send_file, session, stream_with_context
)
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
from ai_engine import (
    analyze_video, detect_anomalies, compute_session_risk,
    generate_forensic_fingerprint, generate_analytics_summary
)

# ═══════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'backend'))
UPLOAD_DIR = os.path.join(BACKEND_DIR, 'uploads')
SHARD_DIR = os.path.join(BACKEND_DIR, 'shards')
ENCRYPTED_DIR = os.path.join(BACKEND_DIR, 'encrypted_shards')
MANIFEST_PATH = os.path.join(BACKEND_DIR, 'manifest.json')
KEY_PATH = os.path.join(BACKEND_DIR, 'secret.key')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov'}
PLAYBACK_HOURS = 3
AUDIT_LOG_PATH = os.path.join(BACKEND_DIR, 'audit_log.json')

SHARD_SIZE_MB = 8                          # Target size per shard (MB)
SHARD_SIZE_BYTES = SHARD_SIZE_MB * 1024 * 1024
MIN_SHARDS = 2                             # Never fewer than 2 shards

for d in [UPLOAD_DIR, SHARD_DIR, ENCRYPTED_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)

# Clean temp on exit
atexit.register(lambda: shutil.rmtree(TEMP_DIR, ignore_errors=True))

# In-memory stores
movies = {}
prepared_videos = {}  # token -> {filepath, expires}
upload_history = []   # list of processed movies


# ═══════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════

def audit_log(action, details=None):
    """Append an entry to the audit log (JSON file + in-memory)."""
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'action': action,
        'details': details or {},
        'ip': request.remote_addr if request else None
    }

    # Load existing log
    log = []
    if os.path.exists(AUDIT_LOG_PATH):
        try:
            with open(AUDIT_LOG_PATH, 'r') as f:
                log = json.load(f)
        except (json.JSONDecodeError, IOError):
            log = []

    log.append(entry)

    # Keep last 500 entries
    log = log[-500:]
    with open(AUDIT_LOG_PATH, 'w') as f:
        json.dump(log, f, indent=2)

    return entry


# ═══════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_video_duration(file_path):
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())


def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            h.update(chunk)
    return h.hexdigest()


def cleanup_dirs():
    """Remove old shards, encrypted shards, and temp files."""
    for d in [SHARD_DIR, TEMP_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    if os.path.exists(ENCRYPTED_DIR):
        for f in os.listdir(ENCRYPTED_DIR):
            os.remove(os.path.join(ENCRYPTED_DIR, f))


def _extract_shard(file_path, start_time, duration, output_path):
    """Extract one shard: input-seek + stream copy (parallel-safe)."""
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-i', file_path,
        '-t', str(duration),
        '-c', 'copy',
        '-avoid_negative_ts', 'make_zero',
        '-movflags', '+faststart',
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def calculate_shards(file_path):
    """Each shard targets ~8 MB. More shards = stronger fragmentation."""
    file_size = os.path.getsize(file_path)
    return max(MIN_SHARDS, math.ceil(file_size / SHARD_SIZE_BYTES))


def shard_video(file_path):
    """
    Split video by running N parallel FFmpeg processes.
    Shard count scales with file size for stronger security on larger files.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    num_shards = calculate_shards(file_path)
    duration = get_video_duration(file_path)
    shard_duration = math.ceil(duration / num_shards)

    tasks = []
    for i in range(num_shards):
        ss = i * shard_duration
        if ss >= duration:
            break
        dur = min(shard_duration, duration - ss)
        out = os.path.join(SHARD_DIR, f'{base_name}_part{i:03d}.mp4')
        tasks.append((ss, dur, out))

    workers = min(len(tasks), os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_extract_shard, file_path, ss, dur, out): out
            for ss, dur, out in tasks
        }
        for future in as_completed(futures):
            future.result()

    shards = [f for f in os.listdir(SHARD_DIR) if os.path.isfile(os.path.join(SHARD_DIR, f))]
    return len(shards)


def encrypt_shards():
    """Encrypt all shards with Fernet. Returns the key bytes."""
    key = Fernet.generate_key()
    fernet = Fernet(key)

    with open(KEY_PATH, 'wb') as f:
        f.write(key)

    shards = sorted([
        f for f in os.listdir(SHARD_DIR)
        if os.path.isfile(os.path.join(SHARD_DIR, f))
    ])

    for shard_file in shards:
        shard_path = os.path.join(SHARD_DIR, shard_file)
        with open(shard_path, 'rb') as f:
            data = f.read()

        encrypted = fernet.encrypt(data)
        enc_path = os.path.join(ENCRYPTED_DIR, shard_file + '.enc')
        with open(enc_path, 'wb') as f:
            f.write(encrypted)

        os.remove(shard_path)

    return key


def generate_manifest(theatre_id='THEATRE_001'):
    """Create manifest.json with SHA-256 hashes and playback window."""
    now = datetime.now(timezone.utc)

    shards = sorted([
        f for f in os.listdir(ENCRYPTED_DIR)
        if os.path.isfile(os.path.join(ENCRYPTED_DIR, f))
    ])

    manifest = {
        'created_at': now.isoformat(),
        'theatre_id': theatre_id,
        'playback_window': {
            'start': now.isoformat(),
            'end': (now + timedelta(hours=PLAYBACK_HOURS)).isoformat()
        },
        'shards': []
    }

    for shard_file in shards:
        shard_path = os.path.join(ENCRYPTED_DIR, shard_file)
        manifest['shards'].append({
            'id': shard_file,
            'sha256': sha256_file(shard_path)
        })

    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=4)

    return manifest


def parse_iso(s):
    """Parse an ISO timestamp, handling both +00:00 and Z suffixes."""
    s = s.rstrip('Z')
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_manifest():
    with open(MANIFEST_PATH, 'r') as f:
        return json.load(f)


def prepare_video(key_str, output_path):
    """Decrypt all shards, verify integrity, and concatenate into one file."""
    manifest = load_manifest()
    if isinstance(key_str, str):
        key_str = key_str.encode()
    fernet = Fernet(key_str)

    with tempfile.TemporaryDirectory() as tmpdir:
        dec_files = []

        for shard_info in manifest['shards']:
            enc_path = os.path.join(ENCRYPTED_DIR, shard_info['id'])
            with open(enc_path, 'rb') as f:
                encrypted = f.read()

            # Integrity check
            actual_hash = hashlib.sha256(encrypted).hexdigest()
            if actual_hash != shard_info['sha256']:
                raise ValueError(f"Integrity check failed: {shard_info['id']}")

            decrypted = fernet.decrypt(encrypted)
            dec_name = shard_info['id'].replace('.enc', '')
            dec_path = os.path.join(tmpdir, dec_name)
            with open(dec_path, 'wb') as f:
                f.write(decrypted)
            dec_files.append(dec_path)
            del decrypted

        # ffmpeg concat list
        list_path = os.path.join(tmpdir, 'concat.txt')
        with open(list_path, 'w') as f:
            for dp in dec_files:
                safe = dp.replace(os.sep, '/')
                f.write(f"file '{safe}'\n")

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', list_path,
            '-c', 'copy',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)


# ═══════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/producer')
def producer_page():
    return render_template('producer.html')


@app.route('/theatre')
def theatre_page():
    return render_template('theatre.html')


# ═══════════════════════════════════════════
# PRODUCER API
# ═══════════════════════════════════════════

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: mp4, mkv, avi, mov'}), 400

    theatre_id = request.form.get('theatre_id', 'THEATRE_001').strip().upper()
    if not theatre_id:
        theatre_id = 'THEATRE_001'

    filename = secure_filename(file.filename)
    movie_id = uuid.uuid4().hex[:8]
    save_path = os.path.join(UPLOAD_DIR, filename)
    file.save(save_path)

    movies[movie_id] = {
        'name': filename,
        'status': 'uploaded',
        'file_path': save_path,
        'key': None,
        'theatre_id': theatre_id
    }

    audit_log('UPLOAD', {'movie_id': movie_id, 'filename': filename, 'theatre_id': theatre_id})
    return jsonify({'movie_id': movie_id, 'filename': filename})


@app.route('/api/process/<movie_id>')
def process_movie(movie_id):
    """SSE endpoint — runs the full pipeline with real-time progress."""
    movie = movies.get(movie_id)
    if not movie:
        return jsonify({'error': 'Movie not found'}), 404

    def generate():
        try:
            # Cleanup
            yield f"data: {json.dumps({'step': 'cleanup', 'message': 'Preparing workspace...', 'progress': 5})}\n\n"
            cleanup_dirs()

            # Shard
            yield f"data: {json.dumps({'step': 'sharding', 'message': 'Splitting video into shards...', 'progress': 15})}\n\n"
            num_shards = shard_video(movie['file_path'])
            audit_log('SHARD', {'movie_id': movie_id, 'shards': num_shards})
            yield f"data: {json.dumps({'step': 'sharding_done', 'message': f'Created {num_shards} shards', 'progress': 40})}\n\n"

            # Encrypt
            yield f"data: {json.dumps({'step': 'encrypting', 'message': 'Encrypting shards with AES...', 'progress': 55})}\n\n"
            key = encrypt_shards()
            movie['key'] = key.decode()
            audit_log('ENCRYPT', {'movie_id': movie_id})
            yield f"data: {json.dumps({'step': 'encrypting_done', 'message': 'All shards encrypted', 'progress': 75})}\n\n"

            # Manifest
            yield f"data: {json.dumps({'step': 'manifest', 'message': 'Generating secure manifest...', 'progress': 85})}\n\n"
            theatre_id = movie.get('theatre_id', 'THEATRE_001')
            manifest = generate_manifest(theatre_id=theatre_id)
            audit_log('MANIFEST', {'movie_id': movie_id, 'theatre_id': theatre_id, 'shards': len(manifest['shards'])})
            yield f"data: {json.dumps({'step': 'manifest_done', 'message': 'Manifest created with SHA-256 hashes', 'progress': 92})}\n\n"

            # AI Analysis
            yield f"data: {json.dumps({'step': 'ai_analysis', 'message': 'Running AI content analysis...', 'progress': 95})}\n\n"
            ai_result = analyze_video(movie['file_path']) if os.path.exists(movie['file_path']) else {}
            quality_score = ai_result.get('quality_score', 'N/A')
            content_tags = ai_result.get('content_tags', [])
            audit_log('AI_ANALYSIS', {'movie_id': movie_id, 'quality_score': quality_score, 'tags': content_tags})
            yield f"data: {json.dumps({'step': 'ai_done', 'message': f'Quality score: {quality_score}/100 — {len(content_tags)} tags', 'progress': 97, 'ai': {'quality_score': quality_score, 'tags': content_tags}})}\n\n"

            # Cleanup uploaded file
            if os.path.exists(movie['file_path']):
                os.remove(movie['file_path'])

            movie['status'] = 'ready'

            # Add to history
            upload_history.append({
                'movie_id': movie_id,
                'name': movie['name'],
                'theatre_id': theatre_id,
                'shards': len(manifest['shards']),
                'processed_at': datetime.now(timezone.utc).isoformat(),
                'key': movie['key']
            })

            audit_log('PIPELINE_COMPLETE', {'movie_id': movie_id})
            yield f"data: {json.dumps({'step': 'done', 'message': 'Pipeline complete!', 'progress': 100, 'key': movie['key'], 'shards': len(manifest['shards'])})}\n\n"

        except Exception as e:
            movie['status'] = 'error'
            yield f"data: {json.dumps({'step': 'error', 'message': str(e), 'progress': 0})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ═══════════════════════════════════════════
# THEATRE API
# ═══════════════════════════════════════════

@app.route('/api/authenticate', methods=['POST'])
def authenticate():
    """Validate the decryption key and prepare the video for streaming."""
    data = request.get_json()
    key = data.get('key', '').strip()

    if not key:
        return jsonify({'error': 'Decryption key is required'}), 400

    if not os.path.exists(MANIFEST_PATH):
        return jsonify({'error': 'No movie available. Ask the producer to upload first.'}), 404

    try:
        manifest = load_manifest()

        # Check playback window
        window = manifest['playback_window']
        start = parse_iso(window['start'])
        end = parse_iso(window['end'])
        now = datetime.now(timezone.utc)

        if now < start:
            return jsonify({
                'error': f"Playback hasn't started yet. Window opens at {start.strftime('%H:%M UTC')}"
            }), 403
        if now > end:
            return jsonify({'error': 'Playback window has expired. Contact producer.'}), 403

        # Validate key by decrypting the first shard
        fernet = Fernet(key.encode())
        first_shard = manifest['shards'][0]
        enc_path = os.path.join(ENCRYPTED_DIR, first_shard['id'])
        with open(enc_path, 'rb') as f:
            fernet.decrypt(f.read())

        # Prepare concatenated video
        token = uuid.uuid4().hex
        output_path = os.path.join(TEMP_DIR, f'{token}.mp4')
        prepare_video(key, output_path)
        prepared_videos[token] = {
            'filepath': output_path,
            'expires': end.isoformat()
        }

        # Purge old prepared videos
        for old_token in list(prepared_videos.keys()):
            if old_token != token:
                old_info = prepared_videos.pop(old_token, None)
                if old_info and os.path.exists(old_info['filepath']):
                    os.remove(old_info['filepath'])

        time_remaining = max(0, int((end - now).total_seconds() / 60))

        audit_log('PLAYBACK_AUTH', {
            'theatre_id': manifest['theatre_id'],
            'time_remaining_min': time_remaining
        })

        return jsonify({
            'success': True,
            'token': token,
            'movie_info': {
                'shards': len(manifest['shards']),
                'theatre_id': manifest['theatre_id'],
                'time_remaining': f'{time_remaining} min',
                'window_end': end.isoformat()
            }
        })

    except Exception as e:
        err = str(e)
        audit_log('PLAYBACK_FAILED', {'error': err})
        if 'Fernet' in err or 'token' in err.lower() or 'padding' in err.lower():
            return jsonify({'error': 'Invalid decryption key'}), 401
        return jsonify({'error': f'Decryption failed: {err}'}), 500


@app.route('/api/stream/<token>')
def stream_video(token):
    """Serve the prepared video with byte-range support for seeking."""
    info = prepared_videos.get(token)
    if not info or not os.path.exists(info['filepath']):
        return 'Video not found or session expired', 404

    # Check if session expired
    if info.get('expires'):
        expires = parse_iso(info['expires'])
        if datetime.now(timezone.utc) > expires:
            # Cleanup
            if os.path.exists(info['filepath']):
                os.remove(info['filepath'])
            prepared_videos.pop(token, None)
            audit_log('STREAM_EXPIRED', {'token': token[:8]})
            return 'Playback window expired', 403

    return send_file(info['filepath'], mimetype='video/mp4', conditional=True)


@app.route('/api/status')
def system_status():
    """Check whether a movie is ready for playback."""
    has_manifest = os.path.exists(MANIFEST_PATH)
    has_shards = (
        os.path.exists(ENCRYPTED_DIR)
        and any(f.endswith('.enc') for f in os.listdir(ENCRYPTED_DIR))
    )

    if has_manifest and has_shards:
        manifest = load_manifest()
        window = manifest['playback_window']
        start = parse_iso(window['start'])
        end = parse_iso(window['end'])
        now = datetime.now(timezone.utc)

        return jsonify({
            'ready': True,
            'shards': len(manifest['shards']),
            'theatre_id': manifest['theatre_id'],
            'playback_active': start <= now <= end,
            'playback_start': window['start'],
            'playback_end': window['end']
        })

    return jsonify({'ready': False})


@app.route('/api/check-expiry/<token>')
def check_expiry(token):
    """Check if a playback token has expired."""
    info = prepared_videos.get(token)
    if not info:
        return jsonify({'expired': True, 'reason': 'Session not found'})

    if info.get('expires'):
        expires = parse_iso(info['expires'])
        now = datetime.now(timezone.utc)
        remaining = max(0, int((expires - now).total_seconds()))
        if remaining == 0:
            return jsonify({'expired': True, 'reason': 'Playback window ended'})
        return jsonify({'expired': False, 'remaining_seconds': remaining})

    return jsonify({'expired': False})


@app.route('/api/history')
def get_history():
    """Return upload processing history."""
    return jsonify(upload_history[::-1])  # newest first


@app.route('/api/audit-log')
def get_audit_log():
    """Return audit trail."""
    if not os.path.exists(AUDIT_LOG_PATH):
        return jsonify([])
    with open(AUDIT_LOG_PATH, 'r') as f:
        log = json.load(f)
    return jsonify(log[::-1])  # newest first


# ═══════════════════════════════════════════
# AI / ML SECURITY INTELLIGENCE
# ═══════════════════════════════════════════

@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html')


@app.route('/api/ai/analyze/<movie_id>')
def ai_analyze(movie_id):
    """Run AI analysis on a movie file (video quality, content tags)."""
    movie = movies.get(movie_id)
    if not movie:
        return jsonify({'error': 'Movie not found'}), 404
    analysis = analyze_video(movie['file_path'])
    audit_log('AI_ANALYZE', {'movie_id': movie_id})
    return jsonify(analysis)


@app.route('/api/ai/threats')
def ai_threats():
    """Anomaly detection on audit log data."""
    result = detect_anomalies(AUDIT_LOG_PATH)
    return jsonify(result)


@app.route('/api/ai/risk-score', methods=['POST'])
def ai_risk_score():
    """Session risk assessment."""
    data = request.get_json() or {}
    theatre_id = data.get('theatre_id', 'UNKNOWN')
    ip = request.remote_addr
    result = compute_session_risk(theatre_id, ip, AUDIT_LOG_PATH)
    return jsonify(result)


@app.route('/api/ai/fingerprint', methods=['POST'])
def ai_fingerprint():
    """Generate forensic fingerprint for a session."""
    data = request.get_json() or {}
    token = data.get('token', 'none')
    theatre_id = data.get('theatre_id', 'UNKNOWN')
    fp = generate_forensic_fingerprint(theatre_id, token, request.remote_addr)
    audit_log('FORENSIC_FP', {'fingerprint': fp['fingerprint_short'], 'theatre_id': theatre_id})
    return jsonify(fp)


@app.route('/api/ai/analytics-summary')
def ai_analytics_summary():
    """Full analytics dashboard data."""
    summary = generate_analytics_summary(AUDIT_LOG_PATH)
    threats = detect_anomalies(AUDIT_LOG_PATH)
    summary['threats'] = threats
    return jsonify(summary)


# ═══════════════════════════════════════════

if __name__ == '__main__':
    print('\n  \033[33m🎬  CinemaShield\033[0m')
    print('  ─────────────────────────────────')
    print('  Home     : http://localhost:5000')
    print('  Producer : http://localhost:5000/producer')
    print('  Theatre  : http://localhost:5000/theatre')
    print('  ─────────────────────────────────\n')
    app.run(debug=True, threaded=True, port=5000)
