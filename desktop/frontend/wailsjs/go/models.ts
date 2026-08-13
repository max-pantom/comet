export namespace main {

	export class Post {
	    post_id: string;
	    username: string;
	    caption: string;
	    create_time?: string;
	    view_count: number;
	    like_count: number;
	    comment_count: number;
	    share_count: number;
	    is_slideshow: boolean;
	    image_count: number;
	    url: string;

	    static createFrom(source: any = {}) {
	        return new Post(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.post_id = source["post_id"];
	        this.username = source["username"];
	        this.caption = source["caption"];
	        this.create_time = source["create_time"];
	        this.view_count = source["view_count"];
	        this.like_count = source["like_count"];
	        this.comment_count = source["comment_count"];
	        this.share_count = source["share_count"];
	        this.is_slideshow = source["is_slideshow"];
	        this.image_count = source["image_count"];
	        this.url = source["url"];
	    }
	}
	export class AccountStats {
	    username: string;
	    posts_last_30d: number;
	    total_views_last_30d: number;
	    max_single_post_views: number;
	    max_single_post_share: number;
	    avg_views_per_post: number;
	    days_active_last_30d: number;
	    passes_default_filters: boolean;

	    static createFrom(source: any = {}) {
	        return new AccountStats(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.username = source["username"];
	        this.posts_last_30d = source["posts_last_30d"];
	        this.total_views_last_30d = source["total_views_last_30d"];
	        this.max_single_post_views = source["max_single_post_views"];
	        this.max_single_post_share = source["max_single_post_share"];
	        this.avg_views_per_post = source["avg_views_per_post"];
	        this.days_active_last_30d = source["days_active_last_30d"];
	        this.passes_default_filters = source["passes_default_filters"];
	    }
	}
	export class AccountReport {
	    account: AccountStats;
	    top_posts: Post[];

	    static createFrom(source: any = {}) {
	        return new AccountReport(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.account = this.convertValues(source["account"], AccountStats);
	        this.top_posts = this.convertValues(source["top_posts"], Post);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

	export class ActivityEntry {
	    id: number;
	    tool_name: string;
	    args: Record<string, any>;
	    reason: string;
	    status: string;
	    result_summary: string;
	    screenshot_path: string;
	    started_at: string;
	    finished_at?: string;

	    static createFrom(source: any = {}) {
	        return new ActivityEntry(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.tool_name = source["tool_name"];
	        this.args = source["args"];
	        this.reason = source["reason"];
	        this.status = source["status"];
	        this.result_summary = source["result_summary"];
	        this.screenshot_path = source["screenshot_path"];
	        this.started_at = source["started_at"];
	        this.finished_at = source["finished_at"];
	    }
	}
	export class Settings {
	    min_delay_seconds: number;
	    max_delay_seconds: number;
	    cache_db_path: string;
	    session_path: string;
	    mcp_port: number;
	    mcp_autostart: boolean;

	    static createFrom(source: any = {}) {
	        return new Settings(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.min_delay_seconds = source["min_delay_seconds"];
	        this.max_delay_seconds = source["max_delay_seconds"];
	        this.cache_db_path = source["cache_db_path"];
	        this.session_path = source["session_path"];
	        this.mcp_port = source["mcp_port"];
	        this.mcp_autostart = source["mcp_autostart"];
	    }
	}
	export class AppState {
	    settings: Settings;
	    settings_path: string;
	    project_root: string;
	    python_path: string;
	    cache_exists: boolean;
	    session_exists: boolean;

	    static createFrom(source: any = {}) {
	        return new AppState(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.settings = this.convertValues(source["settings"], Settings);
	        this.settings_path = source["settings_path"];
	        this.project_root = source["project_root"];
	        this.python_path = source["python_path"];
	        this.cache_exists = source["cache_exists"];
	        this.session_exists = source["session_exists"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class LoginResult {
	    ok: boolean;
	    saved: boolean;
	    session_path: string;
	    auth_cookies: string[];

	    static createFrom(source: any = {}) {
	        return new LoginResult(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.ok = source["ok"];
	        this.saved = source["saved"];
	        this.session_path = source["session_path"];
	        this.auth_cookies = source["auth_cookies"];
	    }
	}
	export class MCPStatus {
	    running: boolean;
	    url: string;
	    port: number;
	    pid: number;
	    autostart: boolean;
	    error: string;

	    static createFrom(source: any = {}) {
	        return new MCPStatus(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.running = source["running"];
	        this.url = source["url"];
	        this.port = source["port"];
	        this.pid = source["pid"];
	        this.autostart = source["autostart"];
	        this.error = source["error"];
	    }
	}

	export class SearchResult {
	    ok: boolean;
	    command: string;
	    cached?: number;
	    count: number;
	    posts: Post[];

	    static createFrom(source: any = {}) {
	        return new SearchResult(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.ok = source["ok"];
	        this.command = source["command"];
	        this.cached = source["cached"];
	        this.count = source["count"];
	        this.posts = this.convertValues(source["posts"], Post);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

}

