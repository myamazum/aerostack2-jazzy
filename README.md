**English** | [日本語](README.ja.md)

[![arXiv](https://img.shields.io/badge/arXiv-2303.18237-b31b1b.svg)](https://arxiv.org/abs/2303.18237) [![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause) [![Build Status ROS2 Package](https://build.ros2.org/job/Hbin_uJ64__aerostack2__ubuntu_jammy_amd64__binary/badge/icon)](https://build.ros2.org/job/Hbin_uJ64__aerostack2__ubuntu_jammy_amd64__binary/) [![codecov_test](https://github.com/aerostack2/aerostack2/actions/workflows/codecov_test.yaml/badge.svg)](https://github.com/aerostack2/aerostack2/actions/workflows/codecov_test.yaml) [![humble](https://github.com/aerostack2/aerostack2/actions/workflows/build-humble.yaml/badge.svg)](https://github.com/aerostack2/aerostack2/actions/workflows/build-humble.yaml) [![Pixi Badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json)](https://pixi.sh)

# Aerostack2 — aerostack2-jazzy fork

Aerostack2 is a ROS 2 framework developed to create autonomous multi-aerial-robots systems in an easy and powerful way.

## About this fork (added by myamazum)

This repository, [myamazum/aerostack2-jazzy](https://github.com/myamazum/aerostack2-jazzy),
is a downstream fork and patch set of [Aerostack2](https://github.com/aerostack2/aerostack2),
maintained by [myamazum](https://github.com/myamazum). Its purpose is to make the
Humble-based Aerostack2 workflow usable with **ROS 2 Jazzy through Pixi / RoboStack
on Ubuntu 22.04 and 24.04**, including existing Ubuntu 22.04 installations.
The fork provides Jazzy defaults, dependency fixes, communication timeouts, and
additional regression tests. Local build and regression verification has been
completed on Ubuntu 22.04.5; Ubuntu 24.04 remains an intended, unverified host target.

### Applying the fork patch to upstream main

The [consolidated patch](patch/aerostack2-jazzy-r2.patch) contains the additions
and modifications maintained by this fork: Pixi/Jazzy configuration and lock
file, dependency fixes, communication timeouts, tests, CI, and documentation.
It combines the earlier Jazzy and communication-timeout patches, so only this
one patch is needed. Build outputs and local test logs are excluded.

The patch targets upstream `main` at commit
[`19c397309c6a41b279e6b551818ec12605cfcecc`](https://github.com/aerostack2/aerostack2/commit/19c397309c6a41b279e6b551818ec12605cfcecc).
That upstream snapshot already includes Jazzy CI, a Jazzy Dockerfile, and an
explicit Pixi `jazzy` environment; this fork builds on that work. Apply the patch
to a clean checkout of this `main` snapshot. Later upstream revisions may require
the patch to be rebased.

For an upstream checkout at that commit, apply the downloaded patch with:

```bash
git apply --check /absolute/path/to/aerostack2-jazzy-r2.patch
git apply /absolute/path/to/aerostack2-jazzy-r2.patch
```

The source in this fork already includes those changes. Pixi is intended for both
Ubuntu 22.04 and 24.04 hosts; the separate Jazzy Docker workflow uses Ubuntu 24.04.
That Docker workflow has not been executed as part of the local verification. Official
[Jazzy Ubuntu binaries](https://docs.ros.org/en/jazzy/Installation/Alternatives/Ubuntu-Install-Binary.html)
target Ubuntu 24.04, while this fork obtains Jazzy from RoboStack inside Pixi.
Humble remains available with `pixi run -e humble ...` and the named Humble Docker tasks.

This fork is maintained independently of the upstream Aerostack2 project.
The build and coverage badges above refer to upstream; fork-specific verification
is recorded in [the verification notes](docs/jazzy/VERIFICATION.md).

See [Jazzy setup and regression tests](docs/jazzy/README.md) for the verification
procedure and remaining platform-specific work. This default selection is not a
claim of completed flight validation or official Jazzy release status.

## Pixi / ROS 2 Jazzy (fork setup)

Use Pixi 0.81.0 or newer. From this repository's root, in a shell without an apt
ROS setup sourced:

```bash
pixi install
pixi run --as-is jazzy-check
pixi run --as-is ros2 pkg prefix as2_core
pixi shell
```

`pixi install` builds the local Aerostack2 packages using `pixi-build-ros` and
installs ROS 2 Jazzy from RoboStack. `ros2 run` and `ros2 launch` are included.
The explicit `-e jazzy` environment is also available. For regression tests:

```bash
pixi install -e jazzy-tests
AS2_TEST_DOMAIN_ID=71 pixi run --as-is -e jazzy-tests jazzy-test
```

Use an unused ROS domain for the tests. See the
[Japanese setup and verification notes](docs/jazzy/README.md) for details.

Versions below 1.0.9 were also developed and tested over ROS 2 galactic (over Ubuntu 20.04), can be found in the branch `EOL/galactic`.

Build the Jazzy image from this checkout with
`docker compose -f docker/compose.yaml build jazzy`. This tests local source,
not an assumed published `aerostack2/jazzy` image. Existing Humble images are
listed at [Aerostack2 Dockerhub](https://hub.docker.com/u/aerostack2).


Most important features:

- Natively developed on ROS 2.
- Complete modularity, allowing elements to be changed or interchanged without affecting the rest of the system.
- Independence of the aerial platform. Easy Sim2Real deployment.
- Project-oriented, allowing to install and use only the necessary packages for the application to be developed. 
- Swarming orientation.

Please visit the [[Aerostack2 Documentation]](https://aerostack2.github.io) for a complete documentation.

Installation instructions can be found [[here]](https://aerostack2.github.io/_00_getting_started/index.html#ubuntu-debian).

<br />

https://user-images.githubusercontent.com/35956525/231999883-e491aa08-2835-47a9-9c68-5b2936e8594e.mp4

<br />

# Credits

Aerostack2 was created by its upstream authors and contributors. Their original
credits, source copyright notices, and [BSD-3-Clause license](LICENSE) are retained.

**Fork author and maintainer: [myamazum](https://github.com/myamazum).**
The contribution credited here is the Pixi / Jazzy adaptation for Ubuntu hosts,
including Ubuntu 22.04, dependency and communication-timeout fixes, additional tests, documentation, and
maintenance of the consolidated patch. For contributions to this fork or upstream,
see [CONTRIBUTING.md](CONTRIBUTING.md).

Original additions in this fork, including the consolidated patch, are also
provided under the [BSD-3-Clause license](LICENSE). Third-party code and
dependencies retain their respective licenses. Attribution to upstream authors
does not imply their endorsement of this fork.

If you use the code in the academic context, please cite:

* M. Fernandez-Cortizas, M. Molina, P. Arias-Perez, R. Perez-Segui,
D. Perez-Saura, and P. Campoy,  2023, ["Aerostack2: A software framework for
developing multi-robot aerial systems"](https://arxiv.org/abs/2303.18237), ArXiv DOI 2303.18237.
