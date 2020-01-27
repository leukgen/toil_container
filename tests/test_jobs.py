"""toil_container jobs tests."""

import argparse
from datetime import datetime
import requests
import time

import pytest

from toil_container import exceptions
from toil_container import jobs
from toil_container import lsf

from .utils import DOCKER_IMAGE
from .utils import SINGULARITY_IMAGE
from .utils import SKIP_DOCKER
from .utils import SKIP_SINGULARITY


def test_call_uses_subprocess():
    options = argparse.Namespace()
    job = jobs.ContainerJob(options)
    assert job.call(["ls"]) == 0
    assert "bin" in job.call(["ls", "/"], check_output=True)

    # check subprocess.CalledProcessError
    with pytest.raises(exceptions.SystemCallError):
        job.call(["rm", "/bin"])

    # check OSError
    with pytest.raises(exceptions.SystemCallError):
        job.call(["florentino-ariza"])


def test_displayname_set_to_class_name_by_default():
    options = argparse.Namespace()
    job = jobs.ContainerJob(options)
    assert job.displayName == job.__class__.__name__


def test_resources_are_encoded():
    options = argparse.Namespace()
    options.batchSystem = "CustomLSF"
    job = jobs.ContainerJob(options, runtime=1, unitName="foo")
    assert lsf._RESOURCES_START_TAG in job.unitName
    assert lsf._RESOURCES_CLOSE_TAG in job.unitName


def assert_image_call(image_attribute, image, tmpdir):
    """Get options namespace."""
    options = argparse.Namespace()
    options.workDir = tmpdir.mkdir("working_dir").strpath
    setattr(options, image_attribute, image)

    # create job and options
    vol1 = tmpdir.mkdir("vol1")
    vol2 = tmpdir.mkdir("vol2")
    options.volumes = [(vol1.strpath, "/vol1"), (vol2.strpath, "/vol2")]

    vol1.join("foo").write("bar")
    job = jobs.ContainerJob(options)

    # test cwd
    assert "bin" in job.call(["ls", ".."], cwd="/bin", check_output=True)

    # test volume
    assert "bar" in job.call(["cat", "/vol1/foo"], check_output=True)
    assert job.call(["ls"]) == 0

    # test env
    cmd = ["bash", "-c", "echo $FOO"]
    assert "BAR" in job.call(cmd, env={"FOO": "BAR"}, check_output=True)

    # check subprocess.CalledProcessError
    with pytest.raises(exceptions.SystemCallError):
        job.call(["rm", "/bin"])

    # check OSError
    with pytest.raises(exceptions.SystemCallError):
        job.call(["florentino-ariza"])

    # test both singularity and docker raiser error
    options = argparse.Namespace()
    options.docker = "foo"
    options.singularity = "bar"
    job = jobs.ContainerJob(options)

    with pytest.raises(exceptions.UsageError) as error:
        job.call(["foo", "bar"])

    assert "use docker or singularity, not both." in str(error.value)


@SKIP_DOCKER
def test_job_with_docker_call(tmpdir):
    assert_image_call("docker", DOCKER_IMAGE, tmpdir)


@SKIP_SINGULARITY
def test_job_with_singularity_call(tmpdir):
    assert_image_call("singularity", SINGULARITY_IMAGE, tmpdir)


def test_call_with_sentry(tmpdir):
    options = argparse.Namespace()
    job = jobs.ContainerJob(options, sentry=True, tool_name="toil_strelka", tool_release="test")

    try:
        job.call(["python", "this.is.a.test.error"], check_output=True)
    except:
        error_time = datetime.utcnow()

    time.sleep(10) # allow sentry api 10 sec to update
    token = '2f257d64885f40da918f8be21e04bbbfe6b1d8c34cad45748631cd315aa70f3b'
    url = 'https://sentry.io/api/0/projects/papaemmelab/toil_strelka/issues/'
    r = requests.get(url=url, headers={'Authorization': f'Bearer {token}'})
    r = r.json()

    success = False
    for error in r:
        title = error['metadata']['value']
        lastSeen = datetime.strptime(error['lastSeen'], '%Y-%m-%dT%H:%M:%S.%fZ')
        delta_time = (error_time - lastSeen).total_seconds()
        if ("this.is.a.test.error" in title) & (delta_time<1):
            issue_id = error['id']
            url = f'https://sentry.io/api/0/issues/{issue_id}/'
            requests.delete(url, headers={'Authorization': f'Bearer {token}'})
            success =  True

    return success
