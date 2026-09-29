"""Generate a private profile containing environment references, never secret values."""
import json
import os
import subprocess
import sys
from pathlib import Path
import yaml
from ingestion.pipeline import ROOT, write_json


def profile(directory, offline=False):
    auth = os.getenv('SNOWFLAKE_AUTHENTICATOR', 'snowflake')
    base = dict(type='snowflake', schema='BRONZE', threads=4,
                client_session_keep_alive=False, query_tag='nyc_taxi_lab',
                session_parameters={'TIMEZONE': 'America/New_York'})
    for name in ('account', 'user', 'role', 'database', 'warehouse'):
        # Offline placeholders only permit dbt parse; never used for execution.
        base[name] = f"{{{{ env_var('SNOWFLAKE_{name.upper()}', 'offline') }}}}" if offline else f"{{{{ env_var('SNOWFLAKE_{name.upper()}') }}}}"
    if auth == 'snowflake_jwt' and not offline:
        base['private_key_path'] = "{{ env_var('SNOWFLAKE_PRIVATE_KEY_FILE') }}"
        if os.getenv('SNOWFLAKE_PRIVATE_KEY_PASSPHRASE'):
            base['private_key_passphrase'] = "{{ env_var('DBT_ENV_SECRET_KEY_PASSPHRASE') }}"
    elif auth == 'externalbrowser' and not offline:
        base['authenticator'] = 'externalbrowser'
    else:
        base['password'] = "{{ env_var('DBT_ENV_SECRET_PASSWORD', 'offline') }}" if offline else "{{ env_var('DBT_ENV_SECRET_PASSWORD') }}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'profiles.yml').write_text(yaml.safe_dump(
        {'nyc_taxi': {'target': 'lab', 'outputs': {'lab': base}}}), encoding='utf-8')
    return directory


def invoke(command, run_directory, offline=False):
    if offline and command != 'parse':
        raise ValueError('Offline profiles are only for parse')
    if not offline:
        from ingestion.snowflake_loader import connection_settings
        connection_settings()  # Normalize lowercase .env aliases in each Kestra process.
    profiles = profile(run_directory / 'profiles', offline)
    environment = os.environ.copy()
    environment['DBT_ENV_SECRET_PASSWORD'] = environment.get('SNOWFLAKE_PASSWORD', '')
    environment['DBT_ENV_SECRET_KEY_PASSPHRASE'] = environment.get('SNOWFLAKE_PRIVATE_KEY_PASSPHRASE', '')
    environment['DBT_SEND_ANONYMOUS_USAGE_STATS'] = 'false'
    executable = Path(sys.executable).with_name('dbt.exe' if os.name == 'nt' else 'dbt')
    target = run_directory / 'target'
    log = run_directory / 'logs'
    arguments = [str(executable), '--no-use-colors', '--log-path', str(log), command,
                 '--project-dir', str(ROOT / 'dbt_project'), '--profiles-dir', str(profiles),
                 '--target-path', str(target)]
    if command == 'parse':
        arguments.append('--no-partial-parse')
    completed = subprocess.run(arguments, env=environment, capture_output=True, text=True)
    # Detailed dbt logs stay local (ignored); do not send credentials/profile details to Kestra logs.
    log.mkdir(parents=True, exist_ok=True)
    (log / f'{command}.txt').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    result = dict(command=command, returncode=completed.returncode, nodes=[])
    artifact = target / 'run_results.json'
    if command != 'parse' and artifact.exists():
        raw = json.loads(artifact.read_text(encoding='utf-8'))
        result['nodes'] = [dict(unique_id=r['unique_id'], status=r['status']) for r in raw['results']]
    write_json(run_directory / f'dbt-{command}.json', result)
    print(json.dumps(dict(dbt_command=command, returncode=completed.returncode,
                          node_count=len(result['nodes']))))
    if completed.returncode != 0:
        raise RuntimeError(f'dbt {command} failed; inspect local log')
    if command == 'test' and (not result['nodes'] or any(r['status'] != 'pass' for r in result['nodes'])):
        raise RuntimeError('All tests must pass; warnings/skips are not acceptance')
    return result
