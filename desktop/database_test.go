package main

import (
	"database/sql"
	"path/filepath"
	"testing"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

func TestCacheQueriesMatchPlaybookStats(t *testing.T) {
	databasePath := filepath.Join(t.TempDir(), "cache.db")
	database, err := sql.Open("sqlite3", databasePath)
	if err != nil {
		t.Fatal(err)
	}
	defer database.Close()

	_, err = database.Exec(`
		CREATE TABLE posts (
			post_id TEXT PRIMARY KEY,
			username TEXT NOT NULL,
			caption TEXT,
			create_time TEXT,
			view_count INTEGER,
			like_count INTEGER,
			comment_count INTEGER,
			share_count INTEGER,
			is_slideshow INTEGER,
			image_count INTEGER,
			url TEXT,
			scraped_at TEXT
		)
	`)
	if err != nil {
		t.Fatal(err)
	}

	now := time.Now().UTC()
	insert := `INSERT INTO posts VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?)`
	rows := []struct {
		id, caption string
		created     time.Time
		views       int64
		slideshow   int
		images      int
	}{
		{"one", "first", now.Add(-24 * time.Hour), 70_000, 1, 5},
		{"two", "second", now.Add(-48 * time.Hour), 50_000, 0, 0},
		{"old", "old post", now.Add(-45 * 24 * time.Hour), 900_000, 0, 0},
	}
	for _, row := range rows {
		if _, err := database.Exec(
			insert,
			row.id,
			"alice",
			row.caption,
			row.created.Format(time.RFC3339),
			row.views,
			row.slideshow,
			row.images,
			"https://www.tiktok.com/@alice/video/"+row.id,
			now.Format(time.RFC3339),
		); err != nil {
			t.Fatal(err)
		}
	}

	app := &App{settings: Settings{CacheDBPath: databasePath}}
	accounts, err := app.ListAccounts()
	if err != nil {
		t.Fatal(err)
	}
	if len(accounts) != 1 {
		t.Fatalf("expected 1 account, got %d", len(accounts))
	}
	account := accounts[0]
	if account.PostsLast30d != 2 || account.TotalViewsLast30d != 120_000 || account.MaxSinglePostViews != 70_000 {
		t.Fatalf("unexpected account stats: %+v", account)
	}
	if account.PassesDefaultFilters {
		t.Fatalf("expected two posts to fail the default minimum of 15: %+v", account)
	}
	if !accountPasses(account, 100_000, 2, 0.7) {
		t.Fatalf("expected account to pass when the post threshold is lowered: %+v", account)
	}

	report, err := app.GetAccountReport("alice")
	if err != nil {
		t.Fatal(err)
	}
	if len(report.TopPosts) != 3 || report.TopPosts[0].PostID != "old" {
		t.Fatalf("top posts were not sorted by views: %+v", report.TopPosts)
	}
}

func TestEmptyAccountReportReturnsZeroStats(t *testing.T) {
	databasePath := filepath.Join(t.TempDir(), "cache.db")
	database, err := sql.Open("sqlite3", databasePath)
	if err != nil {
		t.Fatal(err)
	}
	_, err = database.Exec(`CREATE TABLE posts (
		post_id TEXT PRIMARY KEY, username TEXT NOT NULL, caption TEXT,
		create_time TEXT, view_count INTEGER, like_count INTEGER,
		comment_count INTEGER, share_count INTEGER, is_slideshow INTEGER,
		image_count INTEGER, url TEXT, scraped_at TEXT
	)`)
	database.Close()
	if err != nil {
		t.Fatal(err)
	}

	app := &App{settings: Settings{CacheDBPath: databasePath}}
	report, err := app.GetAccountReport("missing")
	if err != nil {
		t.Fatal(err)
	}
	if report.Account.Username != "missing" || len(report.TopPosts) != 0 {
		t.Fatalf("unexpected empty report: %+v", report)
	}
}
