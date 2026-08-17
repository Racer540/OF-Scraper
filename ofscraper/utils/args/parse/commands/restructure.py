import cloup as click

from ofscraper.utils.args.parse.groups.program import program_options
from ofscraper.utils.args.parse.groups.logging import logging_options


@click.command(
    "restructure",
    help="Move downloaded files to match the current folder layout (dir_format)",
    short_help="restructure downloaded files",
)
@program_options
@logging_options
@click.pass_context
def restructure(ctx, *args, **kwargs):
    return ctx.params, ctx.info_name
