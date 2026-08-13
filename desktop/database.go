package main

import (
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

func (a *App) ReadScreenshot(path string) (string, error) {
	clean := filepath.Clean(path)
	data, err := os.ReadFile(clean)
	if err != nil {
		return "", fmt.Errorf("read screenshot: %w", err)
	}
	return "data:image/png;base64," + base64.StdEncoding.EncodeToString(data), nil
}

func writeActivity(path, tool string, args map[string]any, status, summary string, id int64) (int64, error) {
	database, err := sql.Open("sqlite3", path)
	if err != nil {
		return 0, err
	}
	defer database.Close()
	if _, err := database.Exec(`CREATE TABLE IF NOT EXISTS activity_log (id INTEGER PRIMARY KEY AUTOINCREMENT, tool_name TEXT NOT NULL, args TEXT NOT NULL DEFAULT '{}', reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, result_summary TEXT NOT NULL DEFAULT '', screenshot_path TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL, finished_at TEXT)`); err != nil {
		return 0, err
	}
	now := time.Now().UTC().Format(time.RFC3339Nano)
	if id == 0 {
		raw, _ := json.Marshal(args)
		result, err := database.Exec(`INSERT INTO activity_log (tool_name,args,status,started_at) VALUES (?,?,?,?)`, tool, raw, status, now)
		if err != nil {
			return 0, err
		}
		id, err = result.LastInsertId()
		return id, err
	}
	_, err = database.Exec(`UPDATE activity_log SET status=?, result_summary=?, finished_at=? WHERE id=?`, status, summary, now, id)
	return id, err
}

const (
	defaultMinViews  = int64(100_000)
	defaultMinPosts  = int64(15)
	defaultMaxShare  = 0.7
	accountWindowDay = 30
)

type AccountStats struct {
	Username             string  `json:"username"`
	PostsLast30d         int64   `json:"posts_last_30d"`
	TotalViewsLast30d    int64   `json:"total_views_last_30d"`
	MaxSinglePostViews   int64   `json:"max_single_post_views"`
	MaxSinglePostShare   float64 `json:"max_single_post_share"`
	AverageViewsPerPost  float64 `json:"avg_views_per_post"`
	DaysActiveLast30d    int64   `json:"days_active_last_30d"`
	PassesDefaultFilters bool    `json:"passes_default_filters"`
}

type AccountReport struct {
	Account  AccountStats `json:"account"`
	TopPosts []Post       `json:"top_posts"`
}

type ActivityEntry struct {
	ID             int64          `json:"id"`
	ToolName       string         `json:"tool_name"`
	Args           map[string]any `json:"args"`
	Reason         string         `json:"reason"`
	Status         string         `json:"status"`
	ResultSummary  string         `json:"result_summary"`
	ScreenshotPath string         `json:"screenshot_path"`
	StartedAt      string         `json:"started_at"`
	FinishedAt     *string        `json:"finished_at"`
}

func (a *App) ListActivity(limit int) ([]ActivityEntry, error) {
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	settings := a.settingsSnapshot()
	database, err := openCache(settings.CacheDBPath)
	if os.IsNotExist(err) {
		return []ActivityEntry{}, nil
	}
	if err != nil {
		return nil, err
	}
	defer database.Close()
	rows, err := database.Query(`
		SELECT id, tool_name, args, reason, status, result_summary,
		       screenshot_path, started_at, finished_at
		FROM activity_log ORDER BY id DESC LIMIT ?`, limit)
	if err != nil {
		return nil, fmt.Errorf("query activity: %w", err)
	}
	defer rows.Close()
	entries := make([]ActivityEntry, 0)
	for rows.Next() {
		var entry ActivityEntry
		var rawArgs string
		var finished sql.NullString
		if err := rows.Scan(&entry.ID, &entry.ToolName, &rawArgs, &entry.Reason,
			&entry.Status, &entry.ResultSummary, &entry.ScreenshotPath,
			&entry.StartedAt, &finished); err != nil {
			return nil, fmt.Errorf("read activity: %w", err)
		}
		entry.Args = map[string]any{}
		if err := json.Unmarshal([]byte(rawArgs), &entry.Args); err != nil {
			entry.Args = map[string]any{"raw": rawArgs}
		}
		if finished.Valid {
			entry.FinishedAt = &finished.String
		}
		entries = append(entries, entry)
	}
	return entries, rows.Err()
}

func (a *App) ListAccounts() ([]AccountStats, error) {
	settings := a.settingsSnapshot()
	database, err := openCache(settings.CacheDBPath)
	if os.IsNotExist(err) {
		return []AccountStats{}, nil
	}
	if err != nil {
		return nil, err
	}
	defer database.Close()

	cutoff := time.Now().UTC().AddDate(0, 0, -accountWindowDay).Format(time.RFC3339)
	rows, err := database.Query(`
		SELECT
			username,
			SUM(CASE WHEN datetime(create_time) >= datetime(?) THEN 1 ELSE 0 END),
			COALESCE(SUM(CASE WHEN datetime(create_time) >= datetime(?) THEN view_count ELSE 0 END), 0),
			COALESCE(MAX(CASE WHEN datetime(create_time) >= datetime(?) THEN view_count ELSE 0 END), 0),
			COUNT(DISTINCT CASE WHEN datetime(create_time) >= datetime(?) THEN date(create_time) END)
		FROM posts
		GROUP BY username
		ORDER BY 3 DESC, username COLLATE NOCASE
	`, cutoff, cutoff, cutoff, cutoff)
	if err != nil {
		return nil, fmt.Errorf("query cached accounts: %w", err)
	}
	defer rows.Close()

	accounts := make([]AccountStats, 0)
	for rows.Next() {
		var account AccountStats
		if err := rows.Scan(
			&account.Username,
			&account.PostsLast30d,
			&account.TotalViewsLast30d,
			&account.MaxSinglePostViews,
			&account.DaysActiveLast30d,
		); err != nil {
			return nil, fmt.Errorf("read cached account: %w", err)
		}
		finishAccountStats(&account)
		accounts = append(accounts, account)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read cached accounts: %w", err)
	}
	return accounts, nil
}

func (a *App) GetAccountReport(username string) (AccountReport, error) {
	username = strings.TrimPrefix(strings.TrimSpace(username), "@")
	if username == "" {
		return AccountReport{}, fmt.Errorf("select an account")
	}
	settings := a.settingsSnapshot()
	database, err := openCache(settings.CacheDBPath)
	if os.IsNotExist(err) {
		return AccountReport{Account: AccountStats{Username: username}, TopPosts: []Post{}}, nil
	}
	if err != nil {
		return AccountReport{}, err
	}
	defer database.Close()

	account, err := queryAccount(database, username)
	if err != nil {
		return AccountReport{}, err
	}
	posts, err := queryTopPosts(database, username, 50)
	if err != nil {
		return AccountReport{}, err
	}
	return AccountReport{Account: account, TopPosts: posts}, nil
}

func openCache(path string) (*sql.DB, error) {
	if _, err := os.Stat(path); err != nil {
		return nil, err
	}
	dsn := (&url.URL{Scheme: "file", Path: path}).String() + "?mode=ro&_busy_timeout=5000"
	database, err := sql.Open("sqlite3", dsn)
	if err != nil {
		return nil, fmt.Errorf("open cache database: %w", err)
	}
	database.SetMaxOpenConns(1)
	if err := database.Ping(); err != nil {
		database.Close()
		return nil, fmt.Errorf("open cache database: %w", err)
	}
	return database, nil
}

func queryAccount(database *sql.DB, username string) (AccountStats, error) {
	cutoff := time.Now().UTC().AddDate(0, 0, -accountWindowDay).Format(time.RFC3339)
	account := AccountStats{Username: username}
	err := database.QueryRow(`
		SELECT
			COALESCE(SUM(CASE WHEN datetime(create_time) >= datetime(?) THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN datetime(create_time) >= datetime(?) THEN view_count ELSE 0 END), 0),
			COALESCE(MAX(CASE WHEN datetime(create_time) >= datetime(?) THEN view_count ELSE 0 END), 0),
			COUNT(DISTINCT CASE WHEN datetime(create_time) >= datetime(?) THEN date(create_time) END)
		FROM posts
		WHERE username = ?
	`, cutoff, cutoff, cutoff, cutoff, username).Scan(
		&account.PostsLast30d,
		&account.TotalViewsLast30d,
		&account.MaxSinglePostViews,
		&account.DaysActiveLast30d,
	)
	if err != nil {
		return AccountStats{}, fmt.Errorf("query account stats: %w", err)
	}
	finishAccountStats(&account)
	return account, nil
}

func queryTopPosts(database *sql.DB, username string, limit int) ([]Post, error) {
	rows, err := database.Query(`
		SELECT post_id, username, COALESCE(caption, ''), create_time,
			COALESCE(view_count, 0), COALESCE(like_count, 0),
			COALESCE(comment_count, 0), COALESCE(share_count, 0),
			COALESCE(is_slideshow, 0), COALESCE(image_count, 0), COALESCE(url, '')
		FROM posts
		WHERE username = ?
		ORDER BY COALESCE(view_count, 0) DESC, datetime(create_time) DESC
		LIMIT ?
	`, username, limit)
	if err != nil {
		return nil, fmt.Errorf("query account posts: %w", err)
	}
	defer rows.Close()

	posts := make([]Post, 0)
	for rows.Next() {
		var post Post
		var createTime sql.NullString
		var slideshow int
		if err := rows.Scan(
			&post.PostID,
			&post.Username,
			&post.Caption,
			&createTime,
			&post.ViewCount,
			&post.LikeCount,
			&post.CommentCount,
			&post.ShareCount,
			&slideshow,
			&post.ImageCount,
			&post.URL,
		); err != nil {
			return nil, fmt.Errorf("read account post: %w", err)
		}
		if createTime.Valid {
			post.CreateTime = &createTime.String
		}
		post.IsSlideshow = slideshow != 0
		posts = append(posts, post)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read account posts: %w", err)
	}
	return posts, nil
}

func finishAccountStats(account *AccountStats) {
	if account.TotalViewsLast30d > 0 {
		account.MaxSinglePostShare = float64(account.MaxSinglePostViews) / float64(account.TotalViewsLast30d)
	}
	if account.PostsLast30d > 0 {
		account.AverageViewsPerPost = float64(account.TotalViewsLast30d) / float64(account.PostsLast30d)
	}
	account.PassesDefaultFilters = accountPasses(
		*account,
		defaultMinViews,
		defaultMinPosts,
		defaultMaxShare,
	)
}

func accountPasses(account AccountStats, minViews, minPosts int64, maxShare float64) bool {
	if account.PostsLast30d < minPosts || account.TotalViewsLast30d < minViews {
		return false
	}
	return account.TotalViewsLast30d == 0 || account.MaxSinglePostShare <= maxShare
}
