"""``sbc iot install-pi-docker`` — Docker Engine via get.docker.com over SSH."""

from __future__ import annotations

import subprocess

import click

from rich.markup import escape

from sbc_config.modules.iot.defaults import ENV_PI_SSH, resolve_pi_ssh
from sbc_config.modules.iot.pi_docker_install import (
    GET_DOCKER_SCRIPT_URL,
    classify_install_failure_stderr,
    run_install_via_ssh,
)


@click.command("install-pi-docker")
@click.option(
    "--ssh",
    default=None,
    metavar="USER@HOST",
    envvar=ENV_PI_SSH,
    show_default=f"${ENV_PI_SSH}",
    help=(
        "SSH target for the Pi (e.g. hz42@192.168.8.122). "
        f"Falls back to ${ENV_PI_SSH} when omitted."
    ),
)
@click.option(
    "--remote-user",
    default=None,
    metavar="LOGIN",
    help=(
        "Pi login name for `usermod -aG docker`. Required when --ssh is "
        "host-only (e.g. via ~/.ssh/config) so user cannot be inferred."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the steps that would run; do not connect or install.",
)
@click.option(
    "--skip-verify",
    is_flag=True,
    help="Skip sudo docker version / compose / hello-world after install.",
)
@click.option(
    "--no-add-user-to-docker-group",
    "no_add_group",
    is_flag=True,
    help="Skip `sudo usermod -aG docker <login>` (use sudo docker on the Pi instead).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt (trusts Docker's remote install script).",
)
@click.pass_context
def install_pi_docker_command(
    ctx: click.Context,
    ssh: str | None,
    remote_user: str | None,
    dry_run: bool,
    skip_verify: bool,
    no_add_group: bool,
    yes: bool,
) -> None:
    """Install Docker Engine (+ Compose plugin) on the Pi using Docker's script.

    Streams https://get.docker.com/ from this machine through SSH into
    ``sudo sh`` on the Pi (**curl**|**sh** trust model — see upstream docs).

    Requires **HTTPS** reachability from the laptop to Docker and from the Pi
    to APT mirrors configured by the script. Remote **sudo** should be
    non-interactive (**passwordless sudo**); otherwise use ``ssh -t`` workflows
    outside this command.

    Ref: ``https://docs.docker.com/engine/install/``

    Typical use (from repo root on the laptop)::

        export SBC_IOT_PI_SSH=hz42@192.168.8.122
        uv run sbc iot install-pi-docker
        # re-login or `newgrp docker` on the Pi before docker without sudo

    Related: ``sbc iot sync-to-pi`` for deploying the repo and PEM bundle.
    """
    console = ctx.obj["console"]
    try:
        target = resolve_pi_ssh(ssh)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort from exc

    if not yes and not dry_run:
        console.print(
            "[bold yellow]Warning:[/bold yellow] installs Docker via the upstream "
            f"scripts at [link={GET_DOCKER_SCRIPT_URL}]{GET_DOCKER_SCRIPT_URL}[/link] "
            "piped into [bold]sudo sh[/bold] on the Pi."
        )
        click.confirm("Continue?", abort=True)

    try:
        lines, _procs = run_install_via_ssh(
            target,
            remote_user=remote_user,
            dry_run=dry_run,
            add_docker_group=not no_add_group,
            skip_verify=skip_verify,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.Abort from exc
    except subprocess.CalledProcessError as exc:
        stderr_b = getattr(exc, "stderr", None) or b""
        stdout_b = getattr(exc, "stdout", None) or b""
        kind = classify_install_failure_stderr(stderr_b, stdout_b)
        if kind == "ssh_auth":
            console.print(
                "[red]SSH authentication failed[/red] (could not log in to the Pi). "
                "[bold]This is not a sudo problem yet[/bold] — OpenSSH refused the keys "
                "or credentials before any remote command ran."
            )
        elif kind == "ssh_host":
            console.print("[red]SSH failed:[/red] host name lookup problem.")
        elif kind == "ssh_network":
            console.print(
                "[red]SSH failed:[/red] could not reach host (network / firewall)."
            )
        else:
            console.print("[red]Remote command failed[/red]")
        if exc.stdout:
            console.print(exc.stdout.decode(errors="replace"))
        if exc.stderr:
            console.print(exc.stderr.decode(errors="replace"))
        if kind == "ssh_auth":
            console.print(
                "\n[yellow]Hint:[/yellow] From this machine "
                "[bold]ssh[/bold] must succeed [bold]without typing a password or "
                "key passphrase[/bold] (this tool uses "
                "[bold]-o BatchMode=yes[/bold]). Try [bold]ssh-add[/bold], "
                "fix [bold]~/.ssh/config[/bold] / [bold]IdentityFile[/bold], or verify "
                f"[bold]{ENV_PI_SSH}[/bold] / --ssh. Interactive password login cannot work here. "
                "Example:\n\n"
                f"    ssh {escape(target)}"
            )
        elif kind == "ssh_host":
            console.print("\n[yellow]Hint:[/yellow] Fix the hostname or DNS.")
        elif kind == "ssh_network":
            console.print(
                "\n[yellow]Hint:[/yellow] Ping the Pi, confirm VPN/LAN, firewall."
            )
        else:
            console.print(
                "\n[yellow]Hint:[/yellow] Ensure passwordless [bold]sudo[/bold] on the Pi "
                "for SSH sessions, or run equivalent steps with [bold]ssh -t[/bold] manually. "
                "[bold]BatchMode=yes[/bold] disables interactive SSH auth — fix SSH first."
            )
        raise click.Abort from exc

    if dry_run:
        for ln in lines:
            console.print(ln)
        console.print("[green]Dry-run complete.[/green]")
        return

    console.print("[green]Docker installed and verified on the Pi.[/green]")
    if not no_add_group:
        console.print(
            "[cyan]Tip:[/cyan] log out and back in (or [bold]newgrp docker[/bold]) "
            "on the Pi before using [bold]docker[/bold] without [bold]sudo[/bold]."
        )
