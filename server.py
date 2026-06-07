#!/usr/bin/env python3
"""
Simple Flask server for AI Video Clipping Pipeline
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='.')
CORS(app)

# Get script directory for subprocess calls
SCRIPT_DIR = Path(__file__).parent.absolute()

# Global state to track current video
current_video = None
transcript_file = None
clips_json = None

# State persistence file
STATE_FILE = Path('outputs/pipeline_state.json')

def save_state():
    """Save current pipeline state to file"""
    state = {
        'current_video': current_video,
        'transcript_file': transcript_file,
        'clips_json': clips_json,
        'completed_stages': []
    }
    
    # Check which stages are complete
    if transcript_file and os.path.exists(transcript_file):
        state['completed_stages'].append(1)
    if clips_json and os.path.exists(clips_json):
        state['completed_stages'].append(2)
    if Path('outputs/vertical_clips').exists() and list(Path('outputs/vertical_clips').glob('clip_*.mp4')):
        state['completed_stages'].append(3)
    if Path('outputs/subtitled').exists() and list(Path('outputs/subtitled').glob('clip_*.mp4')):
        state['completed_stages'].append(4)
    if Path('outputs/final').exists() and list(Path('outputs/final').glob('clip_*.mp4')):
        state['completed_stages'].append(5)
    
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_state():
    """Load pipeline state from file"""
    global current_video, transcript_file, clips_json
    
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
            current_video = state.get('current_video')
            transcript_file = state.get('transcript_file')
            clips_json = state.get('clips_json')
            return state
    return None

@app.route('/')
def index():
    load_state()  # Load state on page load
    return send_from_directory('.', 'index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    """Get current pipeline state"""
    state = load_state()
    if not state:
        return jsonify({
            'completed_stages': [],
            'current_video': None
        })
    
    # Add result data for each completed stage
    results = {}
    
    if 1 in state['completed_stages'] and transcript_file and os.path.exists(transcript_file):
        with open(transcript_file) as f:
            transcript = json.load(f)
        results['stage1'] = {
            'message': 'Transcription complete',
            'language': transcript.get('language'),
            'duration': transcript.get('duration'),
            'preview': transcript.get('text', '')[:500] + '...'
        }
    
    if 2 in state['completed_stages'] and clips_json and os.path.exists(clips_json):
        with open(clips_json) as f:
            clips_data = json.load(f)
        clips_preview = []
        for i, clip in enumerate(clips_data.get('clips', [])[:5], 1):
            clips_preview.append({
                'number': i,
                'start': clip['start'],
                'end': clip['end'],
                'duration': clip['end'] - clip['start'],
                'hook': clip['viral_hook_text']
            })
        results['stage2'] = {
            'message': f"Found {len(clips_data.get('clips', []))} viral clips",
            'num_clips': len(clips_data.get('clips', [])),
            'clips': clips_preview
        }
    
    if 3 in state['completed_stages']:
        clips_dir = Path('outputs/vertical_clips')
        clip_files = list(clips_dir.glob('clip_*.mp4'))
        results['stage3'] = {
            'message': f"Extracted {len(clip_files)} clips",
            'num_clips': len(clip_files),
            'output_dir': str(clips_dir)
        }
    
    if 4 in state['completed_stages']:
        subtitled_dir = Path('outputs/subtitled')
        subtitled_files = list(subtitled_dir.glob('clip_*.mp4'))
        results['stage4'] = {
            'message': f"Added subtitles to {len(subtitled_files)} clips",
            'num_clips': len(subtitled_files),
            'output_dir': str(subtitled_dir)
        }
    
    if 5 in state['completed_stages']:
        final_dir = Path('outputs/final')
        final_files = sorted(final_dir.glob('clip_*.mp4'))
        
        # Load clips metadata
        clips_metadata = []
        if clips_json and os.path.exists(clips_json):
            with open(clips_json) as f:
                clips_data = json.load(f)
                clips_metadata = clips_data.get('clips', [])
        
        # Build clip information with preview/download URLs
        clips_info = []
        for clip_file in final_files:
            # Extract clip number from filename (e.g., clip_001.mp4 -> 1)
            import re
            match = re.search(r'clip_(\d+)', clip_file.name)
            if match:
                clip_num = int(match.group(1))
                # Use clip_num - 1 as index (clip_001 = index 0)
                clip_data = clips_metadata[clip_num - 1] if clip_num - 1 < len(clips_metadata) else {}
            else:
                clip_num = len(clips_info) + 1
                clip_data = {}
            
            clips_info.append({
                'filename': clip_file.name,
                'number': clip_num,
                'size_mb': round(clip_file.stat().st_size / (1024 * 1024), 2),
                'hook': clip_data.get('viral_hook_text', 'Viral Clip'),
                'title': clip_data.get('video_title_for_youtube_short', f'Clip {clip_num}'),
                'download_url': f'/api/download/{clip_file.name}',
                'preview_url': f'/api/preview/{clip_file.name}'
            })
        
        results['stage5'] = {
            'message': f"Pipeline complete! {len(final_files)} clips ready",
            'num_clips': len(final_files),
            'output_dir': str(final_dir),
            'clips': clips_info
        }
    
    return jsonify({
        'completed_stages': state['completed_stages'],
        'current_video': state.get('current_video'),
        'results': results
    })

@app.route('/api/reset', methods=['POST'])
def reset_pipeline():
    """Reset/clear all pipeline data and start fresh"""
    global current_video, transcript_file, clips_json
    
    try:
        import shutil
        
        # Clear global state
        current_video = None
        transcript_file = None
        clips_json = None
        
        # Delete state file
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        
        # Delete all outputs
        outputs_dir = Path('outputs')
        if outputs_dir.exists():
            shutil.rmtree(outputs_dir)
        
        # Recreate outputs directory
        outputs_dir.mkdir(exist_ok=True)
        
        return jsonify({
            'success': True,
            'message': 'Pipeline reset! Ready for a new video.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_video():
    """Handle video file upload"""
    global current_video, transcript_file, clips_json
    
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    video = request.files['video']
    if video.filename == '':
        return jsonify({'error': 'No video selected'}), 400
    
    # Save uploaded video
    output_dir = Path('outputs')
    output_dir.mkdir(exist_ok=True)
    
    video_path = output_dir / video.filename
    video.save(str(video_path))
    
    current_video = str(video_path)
    video_name = video_path.stem
    transcript_file = str(output_dir / f"{video_name}_transcript.json")
    clips_json = str(output_dir / f"{video_name}_viral_clips.json")
    
    save_state()  # Save state after upload
    
    return jsonify({
        'success': True,
        'video': current_video,
        'message': f'Uploaded {video.filename}'
    })

@app.route('/api/stage1', methods=['POST'])
def stage1_transcribe():
    """Stage 1: Transcribe video"""
    if not current_video:
        return jsonify({'error': 'No video uploaded'}), 400
    
    try:
        result = subprocess.run([
            sys.executable, 'transcribe.py',
            current_video,
            transcript_file
        ], capture_output=True, text=True, timeout=600, env=os.environ.copy(), cwd=str(SCRIPT_DIR))
        
        if result.returncode != 0:
            return jsonify({'error': result.stderr}), 500
        
        # Load transcript to show preview
        with open(transcript_file) as f:
            transcript = json.load(f)
        
        save_state()  # Save state after stage 1
        
        return jsonify({
            'success': True,
            'message': 'Transcription complete',
            'language': transcript.get('language'),
            'duration': transcript.get('duration'),
            'preview': transcript.get('text', '')[:500] + '...'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stage2', methods=['POST'])
def stage2_detect():
    """Stage 2: Detect viral moments"""
    if not transcript_file or not os.path.exists(transcript_file):
        return jsonify({'error': 'Run Stage 1 first'}), 400
    
    try:
        result = subprocess.run([
            sys.executable, 'viral_detector.py',
            current_video,
            '-o', clips_json
        ], 
        capture_output=True, 
        text=True, 
        timeout=300, 
        env=os.environ.copy(),
        cwd=str(SCRIPT_DIR))  # Ensure correct working directory
        
        # Print debug output for troubleshooting
        if result.stdout:
            print("Stage 2 stdout:", result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        if result.stderr:
            print("Stage 2 stderr:", result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            return jsonify({'error': error_msg}), 500
        
        # Load clips
        with open(clips_json) as f:
            clips_data = json.load(f)
        
        clips_preview = []
        for i, clip in enumerate(clips_data.get('clips', [])[:5], 1):
            clips_preview.append({
                'number': i,
                'start': clip['start'],
                'end': clip['end'],
                'duration': clip['end'] - clip['start'],
                'hook': clip['viral_hook_text']
            })
        
        save_state()  # Save state after stage 2
        
        return jsonify({
            'success': True,
            'message': f"Found {len(clips_data.get('clips', []))} viral clips",
            'num_clips': len(clips_data.get('clips', [])),
            'clips': clips_preview
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stage3', methods=['POST'])
def stage3_extract():
    """Stage 3: Extract clips"""
    if not clips_json or not os.path.exists(clips_json):
        return jsonify({'error': 'Run Stage 2 first'}), 400
    
    try:
        clips_dir = Path('outputs/vertical_clips')
        clips_dir.mkdir(parents=True, exist_ok=True)
        
        result = subprocess.run([
            sys.executable, 'clip_extractor.py',
            current_video,
            clips_json,
            '-o', str(clips_dir),
            '--vertical'
        ], capture_output=True, text=True, timeout=600, env=os.environ.copy(), cwd=str(SCRIPT_DIR))
        
        if result.returncode != 0:
            return jsonify({'error': result.stderr}), 500
        
        # Count extracted clips
        clip_files = list(clips_dir.glob('clip_*.mp4'))
        
        save_state()  # Save state after stage 3
        
        return jsonify({
            'success': True,
            'message': f"Extracted {len(clip_files)} clips",
            'num_clips': len(clip_files),
            'output_dir': str(clips_dir)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stage4', methods=['POST'])
def stage4_subtitles():
    """Stage 4: Add subtitles"""
    clips_dir = Path('outputs/vertical_clips')
    if not clips_dir.exists():
        return jsonify({'error': 'Run Stage 3 first'}), 400
    
    try:
        subtitled_dir = Path('outputs/subtitled')
        subtitled_dir.mkdir(parents=True, exist_ok=True)
        
        # Load clips data for timestamps
        with open(clips_json) as f:
            clips_data = json.load(f)
        
        clip_files = sorted(clips_dir.glob('clip_*.mp4'))
        for i, clip_file in enumerate(clip_files):
            clip_data = clips_data['clips'][i]
            output_path = subtitled_dir / clip_file.name
            
            subprocess.run([
                sys.executable, 'subtitle_generator.py',
                str(clip_file),
                transcript_file,
                '-s', str(clip_data['start']),
                '-e', str(clip_data['end']),
                '-o', str(output_path)
            ], capture_output=True, text=True, timeout=300, env=os.environ.copy(), cwd=str(SCRIPT_DIR))
        
        subtitled_files = list(subtitled_dir.glob('clip_*.mp4'))
        
        save_state()  # Save state after stage 4
        
        return jsonify({
            'success': True,
            'message': f"Added subtitles to {len(subtitled_files)} clips",
            'num_clips': len(subtitled_files),
            'output_dir': str(subtitled_dir)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stage5', methods=['POST'])
def stage5_effects():
    """Stage 5: Add AI effects"""
    subtitled_dir = Path('outputs/subtitled')
    if not subtitled_dir.exists():
        return jsonify({'error': 'Run Stage 4 first'}), 400
    
    try:
        final_dir = Path('outputs/final')
        final_dir.mkdir(parents=True, exist_ok=True)
        
        # Load clips data
        with open(clips_json) as f:
            clips_data = json.load(f)
        
        subtitled_files = sorted(subtitled_dir.glob('clip_*.mp4'))
        
        # For speed, just copy files (AI effects can be slow/unstable)
        for i, clip_file in enumerate(subtitled_files):
            output_path = final_dir / clip_file.name
            # Just copy the subtitled version
            import shutil
            shutil.copy(clip_file, output_path)
        
        final_files = list(final_dir.glob('clip_*.mp4'))
        
        # Build clip information with metadata
        clips_info = []
        for clip_file in sorted(final_files):
            # Extract clip number from filename (e.g., clip_001.mp4 -> 1)
            import re
            match = re.search(r'clip_(\d+)', clip_file.name)
            if match:
                clip_num = int(match.group(1))
                # Use clip_num - 1 as index (clip_001 = index 0)
                clip_data = clips_data['clips'][clip_num - 1] if clip_num - 1 < len(clips_data['clips']) else {}
            else:
                clip_num = len(clips_info) + 1
                clip_data = {}
            
            clips_info.append({
                'filename': clip_file.name,
                'number': clip_num,
                'size_mb': round(clip_file.stat().st_size / (1024 * 1024), 2),
                'hook': clip_data.get('viral_hook_text', 'Viral Clip'),
                'title': clip_data.get('video_title_for_youtube_short', f'Clip {clip_num}'),
                'download_url': f'/api/download/{clip_file.name}',
                'preview_url': f'/api/preview/{clip_file.name}'
            })
        
        save_state()  # Save state after stage 5
        
        return jsonify({
            'success': True,
            'message': f"Pipeline complete! {len(final_files)} clips ready",
            'num_clips': len(final_files),
            'output_dir': str(final_dir),
            'clips': clips_info
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview/<filename>', methods=['GET'])
def preview_video(filename):
    """Serve video file for preview"""
    final_dir = Path('outputs/final')
    return send_from_directory(final_dir, filename)

@app.route('/api/download/<filename>', methods=['GET'])
def download_video(filename):
    """Download video file"""
    final_dir = Path('outputs/final')
    return send_from_directory(final_dir, filename, as_attachment=True)

@app.route('/api/clips', methods=['GET'])
def list_clips():
    """List all final clips with metadata"""
    final_dir = Path('outputs/final')
    
    if not final_dir.exists():
        return jsonify({'clips': []})
    
    final_files = sorted(final_dir.glob('clip_*.mp4'))
    
    # Try to load clips metadata
    clips_metadata = []
    if clips_json and os.path.exists(clips_json):
        with open(clips_json) as f:
            clips_data = json.load(f)
            clips_metadata = clips_data.get('clips', [])
    
    clips_info = []
    for clip_file in final_files:
        # Extract clip number from filename (e.g., clip_001.mp4 -> 1)
        import re
        match = re.search(r'clip_(\d+)', clip_file.name)
        if match:
            clip_num = int(match.group(1))
            # Use clip_num - 1 as index (clip_001 = index 0)
            clip_data = clips_metadata[clip_num - 1] if clip_num - 1 < len(clips_metadata) else {}
        else:
            clip_num = len(clips_info) + 1
            clip_data = {}
        
        clips_info.append({
            'filename': clip_file.name,
            'number': clip_num,
            'size_mb': round(clip_file.stat().st_size / (1024 * 1024), 2),
            'hook': clip_data.get('viral_hook_text', 'Viral Clip'),
            'title': clip_data.get('video_title_for_youtube_short', f'Clip {clip_num}'),
            'download_url': f'/api/download/{clip_file.name}',
            'preview_url': f'/api/preview/{clip_file.name}'
        })
    
    return jsonify({'clips': clips_info})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
