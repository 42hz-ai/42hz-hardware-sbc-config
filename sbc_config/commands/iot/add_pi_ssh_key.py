"""``sbc iot add-pi-ssh-key`` — bootstrap ``authorized_keys`` on the Pi."""

from __future__ import annotations

from pathlib import Path

import click

from rich.markup import escape

from sbc_config.modules.iot.defaults import (
    ENV_PI_SSH,
    ENV_SSH_PUBLIC_KEY,
    resolve_pi_ssh,
)
from sbc_config.modules.iot.pi_ssh_authorize import (
    authorize_pi_ssh,
    resolve_public_key_path,
)


@click.command("add-pi-ssh-key")
@click.option(
    "--ssh",
    default=None,
    metavar="USER@HOST",
    envvar=ENV_PI_SSH,
    show_default=f"${ENV_PI_SSH}",
    help=(
        "SSH target for the Pi (same as sync-to-pi). "
        f"Falls back to ${ENV_PI_SSH} when omitted."
    ),
)
@click.option(
    "--public-key",
    "public_key_opt",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=None,
    metavar="FILE.pub",
    help=(
        "Public key file to install (default: first of ~/.ssh/id_ed25519.pub, "
        f"id_ecdsa.pub, id_rsa.pub, else ${ENV_SSH_PUBLIC_KEY})."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print what would run; do not invoke ssh-copy-id / ssh.",
)
@click.option(
    "--force-append",
    "force_append",
    is_flag=True,
    help=(
        "Skip ssh-copy-id; use built-in ssh+base64 append (needs ssh-copy-id "
        "absent from PATH or experimentation)."
    ),
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation.",
)
@click.pass_context
def add_pi_ssh_key_command(
    ctx: click.Context,
    ssh: str | None,
    public_key_opt: Path | None,
    dry_run: bool,
    force_append: bool,
    yes: bool,
) -> None:
    """Install your SSH public key on the Pi (~/.ssh/authorized_keys).

    Run this once from your laptop **before** passwordless tooling that uses
    ``ssh -o BatchMode=yes`` (e.g. ``install-pi-docker``, ``sync-to-pi``):

    Typical flow — you will be prompted for the Pi user's **SSH password**
    unless you already log in by key::

        export SBC_IOT_PI_SSH=hz42@192.168.8.122
        uv run sbc iot add-pi-ssh-key --dry-run
        uv run sbc iot add-pi-ssh-key

    Uses ``ssh-copy-id`` when available (recommended). Fallback embeds your
    public key via base64 in a remote shell command so stdin stays free for
    OpenSSH interactive prompts.

    Prefer ``ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519`` so ``ssh`` picks the key
    with no ``~/.ssh/config``. Ref: Debian ``ssh-copy-id``, OpenSSH ``authorized_keys``.
    Non-standard private key filenames need ``IdentityFile`` in ``~/.ssh/config``
    (same account as ``uv run sbc``); see ``infra/docker/iot-runner/README.md`` §1.
    """
    console = ctx.obj["console"]
    try:
        target = resolve_pi_ssh(ssh)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort from exc

    try:
        pub_path = resolve_public_key_path(public_key_opt)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort from exc

    if not yes and not dry_run:
        console.print(f"SSH target [bold]{escape(target)}[/bold]")
        console.print(f"Public key file [cyan]{escape(str(pub_path))}[/cyan]")
        click.confirm(
            "Append this key on the Pi (may prompt for password)?", abort=True
        )

    lines, proc = authorize_pi_ssh(
        target,
        pub_key_path=pub_path,
        dry_run=dry_run,
        force_append=force_append,
    )

    if dry_run:
        assert lines is not None
        for ln in lines:
            console.print(ln)
        console.print("[green]Dry-run complete.[/green]")
        return

    if proc is None:
        console.print("[red]Internal error:[/red] subprocess result missing.")
        raise click.Abort

    if proc.returncode != 0:
        console.print(
            "[red]Key install exited non-zero[/red] "
            f"(code={proc.returncode}). "
            "Check SSH password, ``~/.ssh`` permissions on the Pi, "
            "and journald/sshd logs."
        )
        raise click.Abort

    console.print(
        "[green]Public key appended.[/green] Verify with "
        f"`ssh {escape(target)}`. Then rerun tools that require "
        "non-interactive SSH (BatchMode=yes)."
    )
