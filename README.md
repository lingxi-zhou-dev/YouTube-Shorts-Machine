# Ricky Clips

Ricky Clips is an AI-powered application that automatically turns long-form videos into short, vertical clips for TikTok, Instagram Reels, and YouTube Shorts.

The application uses Google Gemini to identify the most engaging moments in a video, then automatically extracts clips, generates subtitles, applies AI enhancements, and exports content ready for social media.

<img width="622" height="1824" alt="image" src="https://github.com/user-attachments/assets/b990a0d9-7401-400d-b82d-0aa9fc72ee04" />

## Features

- AI-powered viral clip detection
- Automatic video transcription
- Vertical (9:16) clip generation
- TikTok-style subtitles
- AI-generated video effects
- YouTube Shorts, TikTok, and Instagram metadata

## Requirements

- Python 3.9+
- FFmpeg
- Google Gemini API Key

## Installation

```bash
git clone <repository-url>
cd "AI Video Clipping Bot"

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file:

```text
GEMINI_API_KEY=your_api_key
```

## Usage

Start the web application:

```bash
python3 server.py
```

Open your browser:

```
http://localhost:5001
```

### Workflow

1. Upload a video.
2. Generate the transcript.
3. Detect viral moments with AI.
4. Extract clips and convert them to vertical format.
5. Add subtitles.
6. Apply AI enhancements.
7. Download the finished clips from:

```
outputs/final/
```

## Project Structure

```
server.py               # Web application
transcribe.py           # Speech-to-text transcription
viral_detector.py       # AI viral clip detection
clip_extractor.py       # Clip extraction & vertical conversion
subtitle_generator.py   # Subtitle generation
ai_effects.py           # AI video enhancements

outputs/
    final/              # Finished clips
```
