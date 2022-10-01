import re

import pytest
from click.testing import CliRunner

import happi
from happi.cli import happi_cli


@pytest.fixture(scope='function')
def client(bad_happi_cfg: str):
    """ misconfigured database """
    return happi.client.Client.from_config(cfg=bad_happi_cfg)


def number_failed_devices(output: str):
    """ Parse cli output for number of failed devices """
    summary_line = [line for line in output.split('\n')
                    if '# devices failed' in line][0]

    match = re.search(r'(\d*) / (\d*)', summary_line)
    return int(match[1])


@pytest.mark.parametrize("n_fails, check", [
   (1, "check_name_match_id"),
   (1, "check_instantiation"),
   (1, "check_extra_info")
   ]
)
def test_audit_cli(
    runner: CliRunner,
    bad_happi_cfg: str,
    n_fails: int,
    check: str
):
    res = runner.invoke(happi_cli, ['--path', bad_happi_cfg, 'audit',
                        '-c', check, '*'])
    # print(runner.invoke(happi_cli, ['--path', bad_happi_cfg, 'search', '*']).ouptut)
    # check that device failed
    print(res.output)
    assert number_failed_devices(res.output) == n_fails
