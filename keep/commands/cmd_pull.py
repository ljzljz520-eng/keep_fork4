import click
import json
import os
from keep import cli, utils, environment
from github import Github


def _repair_entry(fields):
    """Keeps only portable fields from one remote entry.

    A malformed contract drops the contract (entry becomes UNKNOWN)
    rather than aborting the whole pull.
    """
    entry = {
        'desc': fields.get('desc', ''),
        'alias': fields.get('alias', ''),
    }
    contract = fields.get('contract')
    if isinstance(contract, dict):
        try:
            cleaned = environment.clean_contract(contract)
        except ValueError:
            cleaned = None
        if cleaned:
            entry['contract'] = cleaned
    return entry


@click.command('pull', short_help='Pull commands from saved GitHub gist.')
@cli.pass_context
def cli(ctx):
    """Pull commands from saved GitHub gist."""

    commands_file_path = os.path.join(utils.dir_path, 'commands.json')
    token = utils.get_github_token()
    if not token:
        return

    hub = Github(token['token'])
    gist = hub.get_gist(token['gist'])

    gist_url = f"https://gist.github.com/{token['gist']}"
    prompt_str = f"[CRITICAL] Replace local commands with GitHub gist\nGist URL : {gist_url} ?"
    if click.confirm(prompt_str, abort=True):
        pass

    try:
        remote = json.loads(gist.files['commands.json'].content)
    except ValueError:
        click.secho("The gist's commands.json is not valid JSON; aborting.",
                    fg='red')
        return
    if not isinstance(remote, dict):
        click.secho("The gist's commands.json has an unexpected format; "
                    "aborting.", fg='red')
        return

    repaired = {}
    for cmd, fields in remote.items():
        if not isinstance(cmd, str) or not isinstance(fields, dict):
            continue
        repaired[cmd] = _repair_entry(fields)

    """Using `w+` so it create the file if doesn't exist (Issue #64)"""
    with open(commands_file_path, 'w+') as commands_file:
        commands_file.write(json.dumps(repaired))
    click.echo("Done!")
