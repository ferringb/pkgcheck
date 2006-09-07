# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

__all__ = ("default_arches", "arches_option", "arches_options",
    "query_cache_options", "check_uses_query_cache", "overlay_options",
    "profile_options", "check_uses_profiles", "FinalizingOption",
    "_record_arches", "license_options", "abspath", "get_repo_base",
    "debugging_options")

import optparse

from pkgcore_checks import util
from pkgcore.util.compatibility import any
from pkgcore.util.currying import pre_curry
from pkgcore.util.demandload import demandload
demandload(globals(), "os "
    "pkgcore.fs.util:abspath "
    "pkgcore.ebuild:repository "
    "pkgcore.repository:multiplex ")


class FinalizingOption(optparse.Option):

    def __init__(self, *args, **kwds):
        f = kwds.pop("finalizer", None)
        optparse.Option.__init__(self, *args, **kwds)
        if f is not None:
            self.finalize = pre_curry(f, self)

    # we intentionally replace the method; pylint: disable-msg=E0202
    def finalize(self, options, runner):
        raise NotImplementedError(self, "finalize")


default_arches = ["x86", "x86-fbsd", "amd64", "ppc", "ppc-macos", "ppc64",
    "sparc", "mips", "arm", "hppa", "m68k", "ia64", "s390", "sh", "alpha"]
default_arches = tuple(sorted(default_arches))

# prototype requires it; pylint: disable-msg=W0613
def _record_arches(attr, option, opt_str, value, parser):
    setattr(parser.values, attr, tuple(value.split(",")))

arches_option = optparse.Option("-a", "--arches", action='callback',
    callback=pre_curry(_record_arches, "arches"), type='string',  
    default=default_arches,
    help="comma seperated list of what arches to run, defaults to %s" %
        ",".join(default_arches))
arches_options = (arches_option,)


# protocol requires the unused args- pylint: disable-msg=W0613
def enable_query_caching(option_inst, options, runner):
    runner.enable_query_cache = True

query_cache_options = \
    (FinalizingOption("--reset-caching-per-category", action='store_const',
        dest='query_caching_freq', const='cat', finalizer=enable_query_caching,
        help="clear query caching after every category (defaults to every "
            "package)"),

    optparse.Option("--reset-caching-per-package", action='store_const',
        dest='query_caching_freq', const='pkg', default='pkg',
        help="clear query caching after ever package (this is the default)"),

    optparse.Option("--reset-caching-per-version", action='store_const',
        dest='query_caching_freq', const='ver',
        help="clear query caching after ever version (defaults to every "
            "package)")
    )


def check_uses_query_cache(check):
    return any(x in query_cache_options for x in check.requires)

# protocol requires the unused args- pylint: disable-msg=W0613
def overlay_finalize(option_inst, options, runner):
    if options.metadata_src_repo is None:
        options.repo_base = None
        options.src_repo = options.target_repo
        return

    conf = options.pkgcore_conf
    try:
        repo = conf.repo[options.metadata_src_repo]
    except KeyError:
        raise optparse.OptionValueError("overlayed-repo %r isn't a known repo"
            % options.metadata_src_repo)

    if not isinstance(repo, repository.UnconfiguredTree):
        raise optparse.OptionValueError("profile-repo %r isn't a "
            "pkgcore.ebuild.repository.UnconfiguredTree instance; must specify "
            "a raw ebuild repo, not type %r: %r" % (repo.__class__, repo))
    options.src_repo = repo
    options.repo_base = abspath(repo.base)
    runner.search_repo = multiplex.tree(options.target_repo, options.src_repo)


overlay_options = (FinalizingOption("-r", "--overlayed-repo", action='store',
    type='string', dest='metadata_src_repo', finalizer=overlay_finalize,
    help="if the target repository is an overlay, specify the repository name "
        "to pull profiles/license from"),)
    

def get_repo_base(options, throw_error=True, repo=None):
    if getattr(options, "repo_base", None) is not None:
        return options.repo_base
    if repo is None:
        repo = options.src_repo
    if throw_error:
        if not isinstance(repo, repository.UnconfiguredTree):
            raise optparse.OptionValueError("target repo %r isn't a "
                "pkgcore.ebuild.repository.UnconfiguredTree instance; "
                "must specify the PORTDIR repo via --overlayed-repo" % repo)

    return getattr(repo, "base", None)


# protocol requires the unused args- pylint: disable-msg=W0613
def profile_finalize(option_inst, options, runner):
    runner.enable_profiles = True
    if options.profiles_enabled is None:
        options.profiles_enabled = []
    if options.profiles_disabled is None:
        options.profiles_disabled = []
    profile_loc = getattr(options, "profile_dir", None)

    if profile_loc is not None:
        if not os.path.isdir(profile_loc):
            raise optparse.OptionValueError("profile-base location %r doesn't "
                "exist/isn't a dir" % profile_loc)
    else:
        profile_loc = os.path.join(get_repo_base(options), "profiles")
        if not os.path.isdir(profile_loc):
            raise optparse.OptionValueError("repo %r lacks a profiles "
                "directory" % options.src_repo)

    profile_loc = abspath(profile_loc)
    options.profile_func = pre_curry(util.get_profile_from_path, profile_loc)
    options.profile_base_dir = profile_loc


profile_options = \
    (FinalizingOption("--profile-base", action='store', type='string',
        finalizer=profile_finalize, dest="profile_dir", default=None,
        help="filepath to base profiles directory"),

    optparse.Option("--profile-disable-dev", action='store_true',
        default=False, dest='profile_ignore_dev',
        help="disable scanning of dev profiles"),

    optparse.Option("--profile-disable-deprecated", action='store_true',
        default=False, dest='profile_ignore_deprecated',
        help="disable scanning of deprecated profiles"),

    optparse.Option("--profile-disable-profiles-desc", action='store_false',
        default=False, dest='profiles_desc_enabled',
        help="disable loading profiles to scan from profiles.desc, you "
            "will want to enable profiles manually via --profile-enable"),

    optparse.Option('--profile-enable', action='append', type='string',
        dest='profiles_enabled',
        help="specify a profile to scan"),

    optparse.Option('--profile-disable', action='append', type='string',
        dest='profiles_disabled',
        help="specify a profile to ignore"))


def check_uses_profiles(check):
    return any(x in profile_options for x in check.requires)


# protocol requires the unused args- pylint: disable-msg=W0613
def license_finalize(option_inst, options, runner):
    if options.license_dir is None:
        base = get_repo_base(options)
        options.license_dir = os.path.join(base, "licenses")
        if not os.path.isdir(options.license_dir):
            raise optparse.OptionValueError(
                "repo %r doesn't have a license directory, you must specify "
                "one via --license-dir or a different overlayed repo via "
                "--overlayed-repo" % options.src_repo)
    else:
        if not os.path.isdir(options.license_dir):
            raise optparse.OptionValueError(
                "--license-dir %r isn't a directory" % options.license_dir)
    options.license_dir = abspath(options.license_dir)
        

license_options = \
    (FinalizingOption("--license-dir", action='store', type='string',
        finalizer=license_finalize, dest='license_dir', default=None,
        help="filepath to license directory"),)

debugging_options = \
    (optparse.Option("--debug", action='store_true', dest='debug',
        default=False,
        help="disable exception wrapping, bail at first unexpected exception"),)
