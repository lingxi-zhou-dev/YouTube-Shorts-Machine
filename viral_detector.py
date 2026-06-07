"""
Viral Clip Detection using Google Gemini API
Author: AI Video Clipping Bot
Purpose: Analyze video transcripts and identify viral moments for short-form content
"""

import json
import os
from typing import Dict, List, Any
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

VIRAL_PROMPT_TEMPLATE = """You are a senior short-form video editor specializing in TikTok, Instagram Reels, and YouTube Shorts.

Analyze the provided transcript and identify 2-6 MOST VIRAL moments suitable for short-form content.

REQUIREMENTS:
- Each clip must be 15-60 seconds long
- Strong hooks required (first 3 seconds are CRITICAL)
- Natural cuts at silence/pauses preferred
- Include viral_hook_text (max 10 words) - catchy overlay text
- Platform-specific titles and descriptions
- Focus on: jaw-dropping facts, emotional moments, plot twists, actionable tips, or controversy

VIDEO DURATION: {duration} seconds
FULL TRANSCRIPT (truncated):
{transcript}

WORDS WITH TIMESTAMPS (sample):
{words}

Return ONLY valid JSON in this exact format (no extra text, no markdown):
{{
  "shorts": [
    {{
      "start": 12.34,
      "end": 37.90,
      "viral_hook_text": "Did you know this?",
      "video_title_for_youtube_short": "Shocking Discovery 🤯",
      "video_description_for_tiktok": "This changed everything 😱 #viral #fyp",
      "video_description_for_instagram": "Can't believe this! #reels #viral"
    }}
  ]
}}
"""


class ViralDetector:
    """Detects viral moments in video transcripts using Google Gemini API."""
    
    def __init__(self, api_key: str = None, model: str = "gemini-2.5-flash"):
        """
        Initialize the Viral Detector.
        
        Args:
            api_key: Google Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Gemini model to use (gemini-2.5-flash is default, gemini-2.5-pro for better quality)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not found. Set GEMINI_API_KEY in .env file or pass as argument.")
        
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
    
    def detect_viral_clips(
        self, 
        transcript: Dict[str, Any], 
        video_duration: float
    ) -> List[Dict[str, Any]]:
        """
        Detect viral moments in a video transcript.
        
        Args:
            transcript: Transcript dict from transcribe.py with keys:
                       - 'text': full transcript text
                       - 'segments': list of segments with word-level timestamps
                       - 'language': detected language
            video_duration: Duration of the video in seconds
        
        Returns:
            List of viral clip dictionaries with fields:
            - start: start time in seconds
            - end: end time in seconds
            - viral_hook_text: catchy overlay text
            - video_title_for_youtube_short: YouTube Shorts title
            - video_description_for_tiktok: TikTok description with hashtags
            - video_description_for_instagram: Instagram description with hashtags
        """
        # Extract words with timestamps for prompt
        words_data = self._extract_words_from_segments(transcript['segments'])
        
        # Format the prompt - use fewer words to reduce token count
        prompt = VIRAL_PROMPT_TEMPLATE.format(
            duration=video_duration,
            transcript=transcript['text'][:2000],  # Limit transcript length
            words=json.dumps(words_data[:100], indent=2)  # Reduced to 100 words
        )
        
        # Call Gemini API
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=8192,  # Doubled to prevent truncation
                    response_mime_type="application/json",  # Enforce JSON response
                )
            )
            
            # Check if response was truncated
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    print(f"Finish reason: {candidate.finish_reason}")
                    if candidate.finish_reason != 'STOP':
                        print(f"WARNING: Response may be incomplete. Finish reason: {candidate.finish_reason}")
            
            # Parse response - handle potential candidates
            if hasattr(response, 'candidates') and response.candidates:
                result_text = response.candidates[0].content.parts[0].text
            else:
                result_text = response.text
            
            print(f"Received response from Gemini API ({len(result_text)} chars)")
            
            # Try to parse JSON, with repair logic for truncated responses
            try:
                result = json.loads(result_text)
                print("JSON parsed successfully on first try!")
            except json.JSONDecodeError as e:
                print(f"Warning: Initial JSON parse failed: {e}")
                print(f"Response length: {len(result_text)} chars")
                print(f"Attempting to repair truncated JSON...")
                
                # Try to repair the JSON by finding valid portion
                repaired_text = self._repair_truncated_json(result_text)
                try:
                    result = json.loads(repaired_text)
                    print("Successfully repaired and parsed JSON!")
                except json.JSONDecodeError as e2:
                    print(f"Error: JSON repair failed: {e2}")
                    print(f"Repaired response (first 500 chars): {repaired_text[:500]}...")
                    print(f"Repaired response (last 500 chars): {repaired_text[-500:]}")
                    
                    # Last resort: return empty clips with error message
                    print("WARNING: Could not parse API response. Returning empty result.")
                    print("This may be due to API rate limiting or response truncation.")
                    print("Try again in a few moments or with a shorter video.")
                    return []
            
            # Handle both dict and list formats
            if isinstance(result, dict):
                clips = self._validate_clips(result.get('shorts', []), video_duration)
            elif isinstance(result, list):
                clips = self._validate_clips(result, video_duration)
            else:
                print(f"Error: Unexpected response format: {type(result)}")
                return []
            
            return clips
            
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse JSON response from Gemini: {e}")
            print(f"This usually indicates the API response was truncated or malformed.")
            print(f"Try running the detection again or use a shorter video.")
            return []  # Return empty instead of crashing
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            raise
    
    def _extract_words_from_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Extract word-level timestamps from segments.
        
        Args:
            segments: List of segment dictionaries
        
        Returns:
            List of word dictionaries with 'word', 'start', 'end' keys
        """
        words = []
        for segment in segments:
            if 'words' in segment:
                for word_info in segment['words']:
                    words.append({
                        'word': word_info.get('word', ''),
                        'start': word_info.get('start', 0),
                        'end': word_info.get('end', 0)
                    })
        return words
    
    def _repair_truncated_json(self, json_str: str) -> str:
        """
        Attempt to repair truncated JSON by finding valid portion.
        
        Handles common issues:
        - Unterminated strings
        - Missing closing braces/brackets
        - Truncated in middle of object
        
        Args:
            json_str: Potentially truncated JSON string
            
        Returns:
            Repaired JSON string (best effort)
        """
        print(f"Attempting to repair JSON (length: {len(json_str)} chars)")
        print(f"First 200 chars: {json_str[:200]}")
        print(f"Last 200 chars: {json_str[-200:]}")
        
        # Strategy 1: Try to find the last complete object in an array
        # Look for pattern: }] or }, followed by more objects
        # We want to find the last '}' that could close an object in an array
        
        # Count opening structures
        brace_count = 0
        bracket_count = 0
        in_string = False
        escape_next = False
        
        # Find positions of complete objects (where } closes an object at array level)
        complete_object_positions = []
        
        for i, char in enumerate(json_str):
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
                
            if in_string:
                continue
                
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                # If we're at bracket level 1 and brace level 0, we closed an object in the array
                if bracket_count == 1 and brace_count == 0:
                    complete_object_positions.append(i)
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
        
        # Strategy: Use the last complete object position
        if complete_object_positions:
            # Use the last complete object
            last_obj_pos = complete_object_positions[-1]
            # Truncate after the closing brace and add closing bracket
            repaired = json_str[:last_obj_pos + 1] + ']'
            
            # If it starts with {, wrap in { "shorts": ... }
            if repaired.strip().startswith('['):
                repaired = '{"shorts": ' + repaired + '}'
            
            print(f"Repaired: Using last complete object at position {last_obj_pos}")
            print(f"Repaired JSON (first 200 chars): {repaired[:200]}")
            print(f"Repaired JSON (last 200 chars): {repaired[-200:]}")
            return repaired
        
        # Strategy 2: If no complete objects found, try more aggressive repair
        print("No complete objects found, trying aggressive repair...")
        
        # Find the last complete JSON value (looking backward)
        # Remove everything after the last valid complete structure
        
        # Reset counters
        brace_count = 0
        bracket_count = 0
        in_string = False
        escape_next = False
        last_balanced_pos = -1
        
        for i, char in enumerate(json_str):
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"':
                in_string = not in_string
                continue
                
            if in_string:
                continue
                
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                
            # Track last position where we're balanced
            if brace_count == 0 and bracket_count == 0:
                last_balanced_pos = i
        
        if last_balanced_pos > 10:  # At least some content
            print(f"Using last balanced position: {last_balanced_pos}")
            return json_str[:last_balanced_pos + 1]
        
        # Strategy 3: Nuclear option - just try to return an empty but valid structure
        print("Cannot repair JSON, returning minimal valid structure")
        return '{"shorts": []}'
    
    def _validate_clips(
        self, 
        clips: List[Dict], 
        video_duration: float
    ) -> List[Dict]:
        """
        Validate and filter clips based on requirements.
        
        Args:
            clips: List of clip dictionaries from API
            video_duration: Total video duration in seconds
        
        Returns:
            List of validated clips
        """
        validated = []
        
        for clip in clips:
            # Check required fields
            required_fields = [
                'start', 'end', 'viral_hook_text',
                'video_title_for_youtube_short',
                'video_description_for_tiktok',
                'video_description_for_instagram'
            ]
            
            if not all(field in clip for field in required_fields):
                print(f"Warning: Skipping clip with missing fields: {clip}")
                continue
            
            # Validate timing
            start = float(clip['start'])
            end = float(clip['end'])
            duration = end - start
            
            if start < 0 or end > video_duration:
                print(f"Warning: Clip timestamps out of range: {start}-{end}s (video is {video_duration}s)")
                continue
            
            if not (15 <= duration <= 60):
                print(f"Warning: Clip duration {duration}s outside 15-60s range")
                continue
            
            if start >= end:
                print(f"Warning: Invalid clip timing: start={start}, end={end}")
                continue
            
            validated.append(clip)
        
        if len(validated) == 0:
            print("Warning: No valid clips found!")
        
        return validated


def detect_viral_clips(
    transcript: Dict[str, Any], 
    video_duration: float,
    api_key: str = None,
    model: str = "gemini-2.5-flash"
) -> List[Dict[str, Any]]:
    """
    Convenience function to detect viral clips.
    
    Args:
        transcript: Transcript dict from transcribe.py
        video_duration: Duration of the video in seconds
        api_key: Optional Gemini API key (defaults to env var)
        model: Gemini model to use (default: gemini-2.5-flash)
    
    Returns:
        List of viral clip dictionaries
    
    Example:
        >>> from transcribe import transcribe_video
        >>> from viral_detector import detect_viral_clips
        >>> 
        >>> transcript = transcribe_video('video.mp4')
        >>> clips = detect_viral_clips(transcript, video_duration=1800)
        >>> 
        >>> for i, clip in enumerate(clips, 1):
        >>>     print(f"Clip {i}: {clip['start']:.2f}s - {clip['end']:.2f}s")
        >>>     print(f"Hook: {clip['viral_hook_text']}")
    """
    detector = ViralDetector(api_key=api_key, model=model)
    return detector.detect_viral_clips(transcript, video_duration)


# CLI usage
if __name__ == "__main__":
    import sys
    from transcribe import transcribe_video
    
    if len(sys.argv) < 2:
        print("Usage: python viral_detector.py <video_file>")
        print("\nExample:")
        print("  python viral_detector.py sample_video.mp4")
        sys.exit(1)
    
    video_path = sys.argv[1]
    
    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    
    print(f"🎬 Processing: {video_path}")
    print("=" * 60)
    
    # Step 1: Transcribe
    print("\n📝 Step 1: Transcribing video...")
    transcript = transcribe_video(video_path)
    print(f"✅ Transcription complete! Language: {transcript['language']}")
    print(f"📄 Transcript: {transcript['text'][:200]}...")
    
    # Get video duration (rough estimate from last segment)
    video_duration = transcript['segments'][-1]['end'] if transcript['segments'] else 0
    
    # Step 2: Detect viral clips
    print(f"\n🔍 Step 2: Detecting viral moments (Duration: {video_duration:.1f}s)...")
    clips = detect_viral_clips(transcript, video_duration)
    
    print(f"\n✅ Found {len(clips)} viral clips!")
    print("=" * 60)
    
    # Display results
    for i, clip in enumerate(clips, 1):
        duration = clip['end'] - clip['start']
        print(f"\n🎥 Clip {i}: {clip['start']:.2f}s → {clip['end']:.2f}s ({duration:.1f}s)")
        print(f"   Hook: {clip['viral_hook_text']}")
        print(f"   YouTube: {clip['video_title_for_youtube_short']}")
        print(f"   TikTok: {clip['video_description_for_tiktok'][:60]}...")
    
    # Save results
    output_file = video_path.replace('.mp4', '_viral_clips.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'video_file': video_path,
            'duration': video_duration,
            'language': transcript['language'],
            'clips': clips
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_file}")
