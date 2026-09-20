import click
from keep import cli as kcli, utils, environment


@click.group("new", short_help="Create a new entry.", invoke_without_command=True)
@click.option("--cmd", help="The command to save")
@click.option("--desc", help="The description of the command")
@click.option("--alias", default="", help="The alias of the command")
@click.option("--contract", "--env", "contract", is_flag=True,
              help="Generate an editable runtime environment contract "
                   "from this machine")
@kcli.pass_context
def cli(kctx, cmd, desc, alias, contract):
    """Saves a new command, note or command set."""
    ctx = click.get_current_context()
    if ctx.invoked_subcommand is None:
        if not cmd:
            cmd = click.prompt("Command")
        if not desc:
            desc = click.prompt("Description")
        if not alias:
            alias = click.prompt("Alias (optional)", default="")

        saved_contract = None
        if contract:
            saved_contract = utils.edit_contract(
                environment.minimal_contract(cmd))
            if saved_contract is None:
                click.echo("Cancelled: no contract provided, entry not "
                           "saved.")
                return

        utils.save_command(cmd, desc, alias, saved_contract)
        utils.log(kctx, f"Saved the new command - {cmd} - with the description - {desc}.")


@cli.command("notes", short_help="Saves a new note.")
@click.option("--name", help="Name of the note")
@click.option("--text", help="Text of the note")
@kcli.pass_context
def notes(kctx, name, text):
    if not name:
        name = click.prompt("Name")
    if not text:
        template = "# Write your note below\n"
        edited = click.edit(template)
        if not edited:
            click.echo("No note provided.")
            return
        text = "\n".join([line for line in edited.splitlines() if not line.startswith("#")])
    utils.save_note(name, text)
    utils.log(kctx, f"Saved the note - {name}.")


@cli.command("set", short_help="Saves a new set of commands.")
@click.option("--name", help="Name of the set")
@click.option("--commands", multiple=True, help="Commands in the set")
@kcli.pass_context
def set_(kctx, name, commands):
    if not name:
        name = click.prompt("Name")
    if not commands:
        template = "# Enter commands one per line\n"
        edited = click.edit(template)
        if not edited:
            click.echo("No commands provided.")
            return
        commands = [line for line in edited.splitlines() if not line.startswith("#") and line.strip()]
    utils.save_command_set(name, list(commands))
    utils.log(kctx, f"Saved command set - {name}.")

