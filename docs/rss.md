# News feeds on the K3 (issue #5)

Each unit pulls RSS/Atom feeds itself with KOReader's built-in **News Downloader** plugin. It saves
articles as EPUBs on the Kindle for offline reading. The feed list lives in this repo, and the
installer writes it to every unit, so nothing is hand-edited on a Kindle.

## How it fits together

- `src/koreader_d00901/feeds.toml` is the feed list (name, section, URL, item limit, maximum age).
- The installer renders it into the plugin's config, `koreader/news/feed_config.lua`, on the Kindle.
  An existing file that differs is kept as `feed_config.lua.bak`.
- On the Kindle, KOReader's data directory is its install directory, and the plugin reads
  `<data dir>/news/feed_config.lua` (`datastorage.lua` and `newsdownloader.koplugin/main.lua`, KOReader v2026.07.1).

## Getting new articles

1. Turn on Wi-Fi on the Kindle. Wi-Fi works without registering the device.
2. In KOReader's file browser, open the top menu: **Tools** > **News downloader (RSS/Atom)** >
   **Sync news feeds**.
3. When it finishes, it offers to open the download folder (**Go to news folder** in the same menu,
   `koreader/news/`). Each feed's articles are EPUBs there.
4. Turn Wi-Fi off again to save battery (see [battery.md](battery.md)).

To clear old articles: **Settings** > **Delete all downloaded items** in the same menu. The feed list
stays. (Menu labels are from KOReader v2026.07.1's `newsdownloader.koplugin` and
`filemanager_menu_order.lua`.)

## The default list

Thirteen feeds are on by default, in three groups, with small limits and a maximum age so a sync
brings a few recent items rather than a backlog:

| Group | Feeds | Per sync |
| ----- | ----- | -------- |
| Security (act on it) | CISA alerts, Debian security advisories, SANS Internet Storm Center | 5-10 items, last 7 days |
| Engineering | Python Insider, FastAPI releases, PostgreSQL news, uv releases, Cloudflare blog, Julia Evans | 3 items, last 14-30 days |
| Research | arXiv cs.LG (concept drift and intrusion detection), arXiv cs.CR, JMLR, Google Research | 3-5 items, last 3-30 days |

Off by default, ready to switch on: arXiv cs.LG (all), Starlette, Pydantic, SQLAlchemy, Docker,
Proxmox announcements and the OpenWrt forum.

Every URL was checked on 2026-11-05: it returned 200 and parsed as RSS/Atom with dated items.

- **CISA** returned 403 to automated clients during that check. The weekly CI check skips it
  (`check = false`). If the Kindle gets the same, the sync finishes with an "unsupported format"
  notice for that one feed, and the others still download. Set `enabled = false` for it then.
- **arXiv cs.LG** in full is about 445 papers (936 KB) a day, which is heavy for a K3 to parse. The
  default instead uses an arXiv API query limited to concept drift and intrusion detection.

## Changing the list

Edit `feeds.toml` in the repo, then update each unit:

```
koreader-d00901 --only feeds
```

To use your own list without editing the repo, pass `--feeds my-feeds.toml` (CLI or TUI), or type
the path in the TUI's **News feed list** field.

```toml
[[feed]]
name = "Pydantic releases"
section = "engineering"        # security, engineering or research
url = "https://github.com/pydantic/pydantic/releases.atom"
limit = 3                      # items per sync (0 = no limit)
max_age = "30d"                # skip older items: s, m, h, d, w, M, y
full_article = false           # true fetches whole web pages; slow on a K3
enabled = true                 # false = written commented out
check = true                   # false = skipped by the weekly CI check
note = "optional comment shown in the generated config"
```

`python -m koreader_d00901.feeds` lists the feeds. `--lua` prints the generated config, and
`--check` downloads and parses every feed, which is the same check CI runs weekly.

## Reading budget

The limits follow a simple rule: security daily, engineering twice a week, research weekly, about
five items each. If a feed is mostly noise after a month, turn it off.
