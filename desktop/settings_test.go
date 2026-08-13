package main

import "testing"

func TestNormalizeSettingsRejectsReversedDelayRange(t *testing.T) {
	settings := defaultSettings()
	settings.MinDelaySeconds = 10
	settings.MaxDelaySeconds = 4
	if _, err := normalizeSettings(settings); err == nil {
		t.Fatal("expected reversed delay range to fail")
	}
}
