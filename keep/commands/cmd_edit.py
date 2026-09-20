import json
import click
from keep import cli, utils, environment
import os


_OVERRIDES_HEADER = (
    "# Local override mappings -- these are NEVER synced.\n"
    "# Save the file to accept. Delete everything to cancel.\n"
    "# Sections (all optional):\n"
    "#   paths:       declared path -> local path\n"
    "#   env:         declared VAR -> local value\n"
    "#   executables: executable name -> local path\n"
    "#   cwd:         declared cwd path -> local path\n"
)


def _edit_overrides(editor):
    current = environment.read_overrides()
    display = json.dumps(current, indent=2) if current else '{}'
    while True:
        edited = click.edit(_OVERRIDES_HEADER + display + '\n',
                            editor=editor, require_save=False)
        if edited is None:
            return
        text = '\n'.join(line for line in edited.splitlines()
                         if not line.lstrip().startswith('#'))
        if not text.strip():
            click.echo("Cancelled.")
            return
        try:
            cleaned = environment.clean_overrides(json.loads(text))
        except ValueError as err:
            click.secho("Invalid overrides: {}".format(err), fg='red')
            display = text
            continue
        environment.write_overrides(cleaned)
        click.echo("Local overrides updated.")
        return


def _edit_entry_contract(pattern, editor):
    matches = utils.grep_commands(pattern)
    if not matches:
        click.echo('No saved commands matches the pattern {}'.format(pattern))
        return
    selected = utils.select_command(matches)
    if selected < 0:
        return
    cmd, fields = matches[selected]
    initial = fields.get('contract')
    if not initial:
        initial = environment.minimal_contract(cmd)
    updated = utils.edit_contract(initial, editor=editor)
    if updated is None:
        click.echo("Cancelled.")
        return
    commands = utils.read_commands()
    if cmd not in commands:
        click.echo("Entry disappeared before it could be saved.")
        return
    commands[cmd]['contract'] = updated
    utils.write_commands(commands)
    click.echo("Updated the contract of '{}'.".format(cmd))


@click.command('edit', short_help='Edit a saved command.')
@click.option('--editor', help='Editor to use')
@click.option('--contract', metavar='PATTERN',
              help="Edit an existing entry's runtime environment contract")
@click.option('--overrides', is_flag=True,
              help='Edit local (never synced) override mappings')
@cli.pass_context
def cli(ctx, editor, contract, overrides):
    """Edit saved commands."""
    if overrides:
        _edit_overrides(editor)
        return
    if contract:
        _edit_entry_contract(contract, editor)
        return

    commands = utils.read_commands()
    if commands is None:
        click.echo("No commands to edit, Add one by 'keep new'. ")
    else:
        edit_header = "# Unchanged file will abort the operation\n"
        new_commands = utils.edit_commands(commands, editor, edit_header)
        if new_commands and new_commands != commands:
            click.echo("Replace:\n")
            click.secho("\t{}".format('\n\t'.join(utils.format_commands(commands))),
                        fg="green")
            click.echo("With:\n\t")
            click.secho("\t{}".format('\n'.join(utils.format_commands(new_commands))),
                        fg="green")
            if click.confirm("", default=False):
                utils.write_commands(new_commands)
        elif new_commands == {}:
            dir_path = os.path.join(os.path.expanduser('~'), '.keep')
            json_path = os.path.join(dir_path, 'commands.json')
            if click.confirm('Delete all commands ?', abort=True):
                os.remove(json_path)
