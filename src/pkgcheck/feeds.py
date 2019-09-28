"""Package feed transformations."""

from operator import attrgetter

from . import base


class _Collapse(base.Transform):
    """Collapse the input into tuples with a function returning the same val.

    Override keyfunc in a subclass and set the C{transforms} attribute.
    """

    def start(self):
        yield from super().start()
        self.chunk = None
        self.key = None

    def keyfunc(self, pkg):
        raise NotImplementedError(self.keyfunc)

    def feed(self, pkg):
        key = self.keyfunc(pkg)
        if key == self.key:
            # New version for our current package.
            self.chunk.append(pkg)
        else:
            # Package change.
            if self.chunk is not None:
                yield from self.child.feed(tuple(self.chunk))
            self.chunk = [pkg]
            self.key = key

    def finish(self):
        # Deal with empty runs.
        if self.chunk is not None:
            yield from self.child.feed(tuple(self.chunk))
        yield from super().finish()
        self.chunk = None
        self.key = None


class VersionToPackage(_Collapse):

    source = base.versioned_feed
    dest = base.package_feed
    scope = base.package_scope
    cost = 10

    keyfunc = attrgetter('key')


class VersionToCategory(_Collapse):

    source = base.versioned_feed
    dest = base.category_feed
    scope = base.category_scope
    cost = 10

    keyfunc = attrgetter('category')


class RawVersionToRawPackage(_Collapse):

    source = base.raw_versioned_feed
    dest = base.raw_package_feed
    scope = base.package_scope
    cost = 10

    def keyfunc(self, pkg):
        return (pkg.category, pkg.package)


class RawVersionToCategory(VersionToCategory):

    source = base.raw_versioned_feed
    cost = 10


class _PackageOrCategoryToRepo(base.Transform):

    def start(self):
        yield from super().start()
        self.repo = []

    def feed(self, item):
        self.repo.append(item)

    def finish(self):
        yield from self.child.feed(self.repo)
        yield from super().finish()
        self.repo = None


class PackageToRepo(_PackageOrCategoryToRepo):

    source = base.package_feed
    dest = base.repository_feed
    scope = base.repository_scope
    cost = 10


class CategoryToRepo(_PackageOrCategoryToRepo):

    source = base.category_feed
    dest = base.repository_feed
    scope = base.repository_scope
    cost = 10


class PackageToCategory(base.Transform):

    source = base.package_feed
    dest = base.category_feed
    scope = base.category_scope
    cost = 10

    def start(self):
        yield from super().start()
        self.chunk = None
        self.category = None

    def feed(self, item):
        category = item[0].category
        if category == self.category:
            self.chunk.extend(item)
        else:
            if self.chunk is not None:
                yield from self.child.feed(tuple(self.chunk))
            self.chunk = list(item)
            self.category = category

    def finish(self):
        if self.chunk is not None:
            yield from self.child.feed(tuple(self.chunk))
        yield from super().finish()
        self.category = None
        self.chunk = None
