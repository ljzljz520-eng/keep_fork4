import os
import click
from keep import cli, utils, environment


def _preflight(fields, overrides, force):
    """Deterministic check before any arguments are collected.

    Returns True when running may proceed. INCOMPATIBLE is rejected by
    default; UNKNOWN requires explicit acknowledgement. ``force``
    bypasses both gates.
    """
    contract = fields.get('contract')
    if not contract:
        status, checks = environment.UNKNOWN, [
            environment.CheckResult('contract',
                                    'no environment contract declared',
                                    environment.UNKNOWN)]
    else:
        status, checks = environment.evaluate_contract(contract, overrides)

    if status == environment.COMPATIBLE:
        return True

    problems = [check.detail for check in checks
                if check.status != environment.COMPATIBLE]

    if force:
        click.secho("Bypassing environment gate (--force). {}".format(
                    '; '.join(problems)), fg='yellow', err=True)
        return True

    if status == environment.INCOMPATIBLE:
        click.secho("Refusing to run: this command is incompatible with "
                    "the current environment:", fg='red', err=True)
        for problem in problems:
            click.secho("  - {}".format(problem), fg='red', err=True)
        click.secho("Re-run with --force to run it anyway.", fg='red',
                    err=True)
        return False

    # UNKNOWN: explicit confirmation is mandatory.
    click.secho("This command has unknown environment requirements:",
                fg='yellow', err=True)
    for problem in problems:
        click.secho("  - {}".format(problem), fg='yellow', err=True)
    return click.confirm("Run it anyway?", default=False, err=True)


@click.command('run', short_help='Executes a saved command.',
               context_settings=dict(ignore_unknown_options=True))
@click.argument('pattern', required=False)
@click.argument('arguments', nargs=-1, type=click.UNPROCESSED)
@click.option('--safe', is_flag=True, help='Ignore missing arguments')
@click.option('-n', '--no-confirm', is_flag=True, help='Don\'t ask confirm before running')
@click.option('-f', '--force', is_flag=True,
              help='Bypass the environment compatibility gate')
@cli.pass_context
def cli(ctx, pattern, arguments, safe, no_confirm, force):
    """Executes a saved command."""

    if not pattern:
        pattern = "(.*?s)"
    matches = utils.grep_commands(pattern)
    if matches:
        selected = utils.select_command(matches)
        if selected >= 0:
            cmd, fields = matches[selected]
            desc = fields['desc']

            # Gate runs first, before any parameter prompts.
            overrides = environment.read_overrides()
            if not _preflight(fields, overrides, force):
                return

            pcmd = utils.create_pcmd(cmd)
            raw_params, params, defaults = utils.get_params_in_pcmd(pcmd)

            arguments = list(arguments)
            kargs = {}
            for r, p, d in zip(raw_params, params, defaults):
                if arguments:
                    val = arguments.pop(0)
                    click.echo(f"{p}: {val}", err=True)
                    kargs[r] = val
                elif safe:
                    if d:
                        kargs[r] = d
                else:
                    p_default = d if d else None
                    val = click.prompt(f"Enter value for '{p}'", default=p_default, err=True)
                    kargs[r] = val

            final_cmd = utils.substitute_pcmd(pcmd, kargs, safe)
            exec_cmd = environment.adapt_command(
                final_cmd, fields.get('contract'), overrides)

            if no_confirm:
                isconfirmed = True
            else:
                shown = exec_cmd if exec_cmd != final_cmd else final_cmd
                suffix = "" if exec_cmd == final_cmd else \
                    "\n\t(with local environment adaptations applied)"
                command = f"$ {shown} :: {desc}{suffix}"
                isconfirmed = click.confirm(f"Execute\n\t{command}\n?", default=True, err=True)

            if isconfirmed:
                os.system(exec_cmd)

    elif matches == []:
        click.echo(f'No saved commands matches the pattern {pattern}', err=True)
    else:
        click.echo("No commands to run, Add one by 'keep new'. ", err=True)
