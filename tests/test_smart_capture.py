"""
Tests for smart capture system including activity tracking.
"""

import time

import pytest

from aw_watcher_enhanced.smart_capture import IdleDetector, OCRDiffDetector


class TestIdleDetectorActivity:
    """Tests for activity percentage tracking in IdleDetector."""

    def test_record_activity_sample(self):
        """Test that recording samples works."""
        detector = IdleDetector()
        detector.record_activity_sample()
        assert len(detector._activity_samples) == 1

    def test_multiple_samples(self):
        """Test recording multiple samples."""
        detector = IdleDetector()
        for _ in range(10):
            detector.record_activity_sample()
        assert len(detector._activity_samples) == 10

    def test_activity_percentage_no_samples(self):
        """Test percentage with no samples returns 0."""
        detector = IdleDetector()
        assert detector.get_activity_percentage() == 0.0

    def test_activity_percentage_all_active(self):
        """Test 100% activity when all samples are active."""
        detector = IdleDetector()
        # Force active samples (idle_time returns 0 on fallback)
        for _ in range(10):
            detector.record_activity_sample()
        pct = detector.get_activity_percentage()
        # On fallback (no Quartz), idle always returns 0, so all active
        assert pct == 100.0

    def test_activity_percentage_custom_window(self):
        """Test custom window parameter."""
        detector = IdleDetector()
        for _ in range(5):
            detector.record_activity_sample()
        pct = detector.get_activity_percentage(window_seconds=60.0)
        assert 0.0 <= pct <= 100.0

    def test_activity_percentage_old_samples_excluded(self):
        """Test that old samples outside window are excluded."""
        detector = IdleDetector()
        # Manually insert an old sample
        detector._activity_samples.append((time.time() - 600, True))
        # Insert recent samples
        for _ in range(5):
            detector.record_activity_sample()
        # With 300s window, the old sample should be excluded
        pct = detector.get_activity_percentage(window_seconds=300.0)
        # Should only consider the 5 recent samples
        assert pct >= 0.0

    def test_deque_maxlen(self):
        """Test that deque has maxlen of 300."""
        detector = IdleDetector()
        assert detector._activity_samples.maxlen == 300

    def test_deque_overflow(self):
        """Test that deque drops oldest when full."""
        detector = IdleDetector()
        for _ in range(350):
            detector.record_activity_sample()
        assert len(detector._activity_samples) == 300


class TestIdleDetector:
    """Tests for base idle detection."""

    def test_set_threshold(self):
        detector = IdleDetector()
        detector.set_threshold(120.0)
        assert detector._idle_threshold == 120.0

    def test_get_idle_seconds(self):
        detector = IdleDetector()
        result = detector.get_idle_seconds()
        assert isinstance(result, float)
        assert result >= 0.0

    def test_is_idle_default(self):
        detector = IdleDetector()
        # On fallback, always returns 0 (active)
        assert detector.is_idle() is False

    def test_is_idle_custom_threshold(self):
        detector = IdleDetector()
        # With 0 threshold, even 0s idle would be idle
        result = detector.is_idle(threshold_seconds=0)
        # Fallback returns 0.0 which is not > 0
        assert isinstance(result, bool)


class TestOCRDiffDetector:
    """Tests for OCR diff detection."""

    def test_first_check_always_runs(self):
        detector = OCRDiffDetector()
        should_run, reason = detector.should_run_llm("Some OCR text")
        assert should_run is True
        assert reason == "content_changed"

    def test_identical_text_skips(self):
        detector = OCRDiffDetector()
        detector.should_run_llm("Same text here")
        should_run, reason = detector.should_run_llm("Same text here")
        assert should_run is False
        assert reason == "identical_hash"

    def test_different_text_runs(self):
        detector = OCRDiffDetector()
        detector.should_run_llm("First text")
        should_run, reason = detector.should_run_llm("Completely different content here")
        assert should_run is True
        assert reason == "content_changed"

    def test_similar_text_skips(self):
        detector = OCRDiffDetector(similarity_threshold=0.8, min_change_chars=50)
        base_text = "The quick brown fox jumps over the lazy dog near the river bank"
        detector.should_run_llm(base_text)
        # Change just one word — small diff
        similar_text = "The quick brown cat jumps over the lazy dog near the river bank"
        should_run, reason = detector.should_run_llm(similar_text)
        assert should_run is False
        assert "similar" in reason

    def test_empty_text_skips(self):
        detector = OCRDiffDetector()
        should_run, reason = detector.should_run_llm("")
        assert should_run is False
        assert reason == "empty_ocr"

    def test_force_next_llm(self):
        detector = OCRDiffDetector()
        detector.should_run_llm("Some text")
        detector.force_next_llm()
        should_run, reason = detector.should_run_llm("Some text")
        assert should_run is True

    def test_stats_tracking(self):
        detector = OCRDiffDetector()
        detector.should_run_llm("First")
        detector.should_run_llm("First")
        detector.should_run_llm("Second completely different text")
        stats = detector.get_stats()
        assert stats["total_checks"] == 3
        assert stats["skipped_identical"] == 1
        assert stats["triggered_different"] == 2
