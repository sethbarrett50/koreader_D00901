"""Generate src/koreader_d00901/k3-status.json, the Grafana dashboard drawn on the K3 (#4).

Kept as a script so the panel layout stays readable and reviewable; run `make dashboard-json`
after editing. The queries are the ones in home_lab_docs' Infrastructure Overview dashboard.
Rendered at 1200x1600 and halved to the K3's 600x800, so sizes here are for that 1200px canvas.
"""

import json

from pathlib import Path

DS = {'type': 'prometheus', 'uid': '${DS_PROMETHEUS}'}
OUT = Path(__file__).resolve().parent.parent / 'src' / 'koreader_d00901' / 'k3-status.json'

# Black on white: anything that needs attention is black, everything fine is mid grey.
BAD, OK, NEUTRAL = '#000000', '#8c8c8c', '#404040'


def query(ref: str, expr: str, legend: str, *, table: bool = False) -> dict:
    return {
        'refId': ref,
        'datasource': DS,
        'expr': expr,
        'legendFormat': legend,
        'instant': True,
        'range': False,
        'format': 'table' if table else 'time_series',
    }


def updown_stat(pid: int, title: str, grid: dict, targets: list[dict]) -> dict:
    return {
        'id': pid,
        'type': 'stat',
        'title': title,
        'gridPos': grid,
        'datasource': DS,
        'targets': targets,
        'options': {
            'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
            'colorMode': 'background',
            'graphMode': 'none',
            'textMode': 'value_and_name',
            'orientation': 'horizontal',
            'justifyMode': 'auto',
            'wideLayout': True,
            'text': {'titleSize': 26, 'valueSize': 30},
        },
        'fieldConfig': {
            'defaults': {
                'mappings': [
                    {
                        'type': 'value',
                        'options': {
                            '0': {'text': 'DOWN', 'color': BAD, 'index': 0},
                            '1': {'text': 'up', 'color': OK, 'index': 1},
                        },
                    }
                ],
                'noValue': 'NO DATA',
                'color': {'mode': 'thresholds'},
                'thresholds': {'mode': 'absolute', 'steps': [{'color': BAD, 'value': None}, {'color': OK, 'value': 1}]},
            },
            'overrides': [],
        },
    }


def percent_bars(pid: int, title: str, grid: dict, job: str) -> dict:
    cpu = f'100 - (avg(rate(node_cpu_seconds_total{{mode="idle",job="{job}"}}[5m])) * 100)'
    ram = f'(1 - (node_memory_MemAvailable_bytes{{job="{job}"}} / node_memory_MemTotal_bytes{{job="{job}"}})) * 100'
    disk = (
        f'100 - ((node_filesystem_avail_bytes{{job="{job}",mountpoint="/",fstype!="tmpfs"}}'
        f' / node_filesystem_size_bytes{{job="{job}",mountpoint="/",fstype!="tmpfs"}}) * 100)'
    )
    return {
        'id': pid,
        'type': 'bargauge',
        'title': title,
        'gridPos': grid,
        'datasource': DS,
        'targets': [query('A', cpu, 'CPU'), query('B', ram, 'RAM'), query('C', disk, 'Disk')],
        'options': {
            'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
            'orientation': 'horizontal',
            'displayMode': 'basic',
            'valueMode': 'text',
            'showUnfilled': True,
            'namePlacement': 'left',
            'text': {'titleSize': 24, 'valueSize': 26},
        },
        'fieldConfig': {
            'defaults': {
                'unit': 'percent',
                'decimals': 0,
                'min': 0,
                'max': 100,
                'color': {'mode': 'thresholds'},
                'thresholds': {
                    'mode': 'absolute',
                    'steps': [{'color': OK, 'value': None}, {'color': BAD, 'value': 85}],
                },
            },
            'overrides': [],
        },
    }


def gpu_stat(pid: int, grid: dict) -> dict:
    job = 'job="llm-01-gpu"'
    return {
        'id': pid,
        'type': 'stat',
        'title': 'llm-01 GPU (P4000)',
        'gridPos': grid,
        'datasource': DS,
        'targets': [
            query('A', f'nvidia_gpu_utilization_percent{{{job}}}', 'Load %'),
            query(
                'B', f'100 * nvidia_gpu_memory_used_bytes{{{job}}} / nvidia_gpu_memory_total_bytes{{{job}}}', 'VRAM %'
            ),
            query('C', f'nvidia_gpu_temperature_celsius{{{job}}}', 'Temp °C'),
        ],
        'options': {
            'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
            'colorMode': 'value',
            'graphMode': 'none',
            'textMode': 'value_and_name',
            'orientation': 'vertical',
            'justifyMode': 'center',
            'text': {'titleSize': 24, 'valueSize': 44},
        },
        'fieldConfig': {
            'defaults': {
                'decimals': 0,
                'noValue': 'NO DATA',
                'color': {'mode': 'fixed', 'fixedColor': NEUTRAL},
            },
            'overrides': [],
        },
    }


def jobs_table(pid: int, grid: dict) -> dict:
    return {
        'id': pid,
        'type': 'table',
        'title': 'CI runners: running jobs',
        'gridPos': grid,
        'datasource': DS,
        'targets': [query('A', 'gha_runner_current_job == 1', '', table=True)],
        'options': {'showHeader': True, 'cellHeight': 'md', 'footer': {'show': False}},
        'fieldConfig': {
            'defaults': {'custom': {'align': 'left'}, 'noValue': 'all runners idle'},
            'overrides': [],
        },
        'transformations': [
            {
                'id': 'organize',
                'options': {
                    'excludeByName': {'Time': True, 'Value': True, '__name__': True, 'instance': True},
                    'renameByName': {'runner': 'Runner', 'job': 'Job'},
                },
            }
        ],
    }


def clock(pid: int, grid: dict) -> dict:
    # Shows when the image was rendered, so a stale screen is obvious.
    return {
        'id': pid,
        'type': 'stat',
        'title': '',
        'gridPos': grid,
        'datasource': DS,
        'targets': [query('A', 'time() * 1000', 'Rendered')],
        'options': {
            'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
            'colorMode': 'none',
            'graphMode': 'none',
            'textMode': 'value_and_name',
            'justifyMode': 'center',
            'text': {'titleSize': 22, 'valueSize': 26},
        },
        'fieldConfig': {'defaults': {'unit': 'dateTimeAsLocal', 'color': {'mode': 'fixed', 'fixedColor': NEUTRAL}}},
    }


def dashboard() -> dict:
    up = [
        query('A', 'up', '{{job}}'),
        query('B', 'caddy_reverse_proxy_upstreams_healthy{job="caddy"}', 'caddy → {{upstream}}'),
    ]
    panels = [
        updown_stat(1, 'Targets', {'x': 0, 'y': 0, 'w': 24, 'h': 15}, up),
        percent_bars(2, 'Proxmox host', {'x': 0, 'y': 15, 'w': 12, 'h': 8}, 'proxmox-node'),
        percent_bars(3, 'monitor-01', {'x': 12, 'y': 15, 'w': 12, 'h': 8}, 'monitor-01-node'),
        gpu_stat(4, {'x': 0, 'y': 23, 'w': 24, 'h': 7}),
        jobs_table(5, {'x': 0, 'y': 30, 'w': 24, 'h': 9}),
        clock(6, {'x': 0, 'y': 39, 'w': 24, 'h': 3}),
    ]
    return {
        '__inputs': [
            {
                'name': 'DS_PROMETHEUS',
                'label': 'Prometheus',
                'type': 'datasource',
                'pluginId': 'prometheus',
                'pluginName': 'Prometheus',
            }
        ],
        'uid': 'k3-status',
        'title': 'K3 status',
        'description': 'Drawn on Kindle Keyboard e-ink displays by koreader-d00901 (#4). Rendered at 1200x1600.',
        'tags': ['k3', 'e-ink'],
        'timezone': 'browser',
        'editable': True,
        'graphTooltip': 0,
        'refresh': '',
        'time': {'from': 'now-15m', 'to': 'now'},
        'schemaVersion': 41,
        'panels': panels,
        'templating': {'list': []},
        'annotations': {'list': []},
        'links': [],
    }


if __name__ == '__main__':
    OUT.write_text(json.dumps(dashboard(), indent=2, ensure_ascii=False) + '\n')
    print(f'wrote {OUT}')
