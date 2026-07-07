import os
import pytest
from unittest.mock import MagicMock, patch
from engines.transcript_engine import TranscriptEngine

def test_format_to_strategic_label():
    # We can mock genai.Client so we don't need a real API key during instantiating the engine
    with patch('google.genai.Client') as mock_client:
        engine = TranscriptEngine()
        
        # Test seconds to [MM:SS] format
        assert engine.format_to_strategic_label(5.0) == "[00:05]"
        assert engine.format_to_strategic_label(65.0) == "[01:05]"
        assert engine.format_to_strategic_label(59.9) == "[00:59]"
        
        # Test hours [HH:MM:SS] format
        assert engine.format_to_strategic_label(3605.0) == "[01:00:05]"
        assert engine.format_to_strategic_label(7265.5) == "[02:01:05]"
        
        # Test boundary cases
        assert engine.format_to_strategic_label(0.0) == "[00:00]"
        assert engine.format_to_strategic_label(-10.0) == "[00:00]"

print("✅ Transcript Engine Unit Test definition loaded")
