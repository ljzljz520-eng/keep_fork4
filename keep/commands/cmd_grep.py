import click
from keep import cli, utils


@click.command('grep', short_help='Searches for a saved command.')
@click.argument('pattern')
@cli.pass_context
def cli(ctx, pattern):
    """Searches for a saved command."""
    matches = utils.grep_commands(pattern)
    if matches:
        for cmd, fields in matches:
            status = utils.entry_status(fields)
            click.secho("[{}] ".format(utils.status_token(status)),
                        nl=False, fg=utils.status_color(status))
            click.secho("$ {} :: {}".format(cmd, fields['desc']), fg='green')
    elif matches == []:
        click.echo('No saved commands matches the pattern {}'.format(pattern))
    else:
        click.echo('No commands to show. Add one by `keep new`.')
