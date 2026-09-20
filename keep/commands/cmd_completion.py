from shlex import quote

import click
from keep import cli, utils


@click.command('completion', short_help='Command completion helper.')
@click.option('--bash', 'shell', flag_value='bash', default=True)
@click.option('--zsh', 'shell', flag_value='zsh')
@cli.pass_context
def cli(ctx, shell):
    """Completion helpers for keep"""
    commands = utils.read_commands()
    if not commands:
        return

    if shell == 'zsh':
        # zsh _describe renders the text after ':' as the description;
        # the compatibility marker rides along in that description.
        for cmd, fields in commands.items():
            token = utils.status_token(utils.entry_status(fields))
            print("{cmd}:[{token}] {desc}".format(
                cmd=cmd, token=token, desc=fields['desc']))
    elif shell == 'bash':
        # Plain bash completion has no per-candidate description channel,
        # so only the command words are emitted.
        for cmd in commands.keys():
            print(quote(cmd))
