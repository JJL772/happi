"""
Backend implemenation using simplejson
"""
import contextlib
import itertools
import os
import os.path
import logging

import simplejson as json

from .core import _Backend
from ..errors import SearchError, DuplicateError

logger = logging.getLogger(__name__)


try:
    import fcntl
except ImportError:
    logger.warning("Unable to import 'fcntl'. Will be unable to lock files")
    fcntl = None


@contextlib.contextmanager
def _load_and_store_context(backend):
    '''
    A context manager to load, and optionally store the JSON database at the end
    '''
    db = backend._load_or_initialize()
    yield db
    backend.store(db)


class JSONBackend(_Backend):
    """
    JSON database

    The happi information is kept in a single dictionary large dictionary that
    is stored using `simplejson`

    Parameters
    ----------
    path : str
        Path to JSON file

    initialze : bool, optional
        Initialize a new empty JSON file to begin filling
    """
    def __init__(self, path, initialize=False):
        self.path = path
        # Create a new JSON file if requested
        if initialize:
            self.initialize()

    def _load_or_initialize(self):
        '''
        Load an existing database or initialize a new one.
        '''
        try:
            return self.load()
        except FileNotFoundError as ex:
            logger.debug('Initializing new database')

        self.initialize()
        return self.load()

    @property
    def all_devices(self):
        """
        All of the devices in the database
        """
        json = self._load_or_initialize()
        return list(json.values())

    def initialize(self):
        """
        Initialize a new JSON file database

        Raises
        ------
        PermissionError:
            If the JSON file specified by `path` already exists

        Notes
        -----
        This is exists because the `store` and `load` methods assume that the
        given path already points to a readable JSON file. In order to begin
        filling a new database, an empty but valid JSON file is created
        """
        # Do not overwrite existing databases
        if os.path.exists(self.path) and os.stat(self.path).st_size > 0:
            raise PermissionError("File {} already exists. Can not initialize "
                                  "a new database.".format(self.path))
        # Dump an empty dictionary
        self.store({})

    def load(self):
        """
        Load the JSON database
        """
        with open(self.path, 'r') as f:
            raw_json = f.read()

        # Allow for empty files to be considered valid databases:
        return json.loads(raw_json) if raw_json else {}

    def store(self, db):
        """
        Stache the database back into JSON

        Parameters
        ----------
        db : dict
            Dictionary to store in JSON

        Raises
        ------
        BlockingIOError:
            If the file is already being used by another happi operation
        """
        with open(self.path, 'w+') as f:
            # Create lock in filesystem
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Dump to file
            try:
                json.dump(db, f, sort_keys=True, indent=4)

            finally:
                if fcntl is not None:
                    # Release lock in filesystem
                    fcntl.flock(f, fcntl.LOCK_UN)

    def _iterative_compare(self, _id, comparison):
        """
        Yields documents which either match ``_id`` or such that the predicate
        ``comparison(name, doc)`` returns True.

        Parameters
        ----------
        _id : str or None
            ID of device
        comparison : callable
            A comparison function with a signature of (device_id, doc)
        """
        db = self._load_or_initialize()
        if not db:
            return

        try:
            yield db[_id]
            # If an _id match exists, exit early
            return
        except KeyError:
            ...

        for name, doc in db.items():
            try:
                if comparison(name, doc):
                    yield doc
            except Exception as ex:
                logger.debug('Comparison method failed: %s', ex, exc_info=ex)

    def find(self, _id=None, multiples=False, **kwargs):
        """
        Find an instance or instances that matches the search criteria

        Parameters
        ----------
        multiples : bool
            Find a single result or all results matching the provided
            information

        kwargs :
            Requested information
        """
        def comparison(name, doc):
            # Find devices matching kwargs
            return all(value == doc[key]
                       for key, value in kwargs.items())

        gen = self._iterative_compare(_id, comparison)
        if multiples:
            return list(gen)

        matches = list(itertools.islice(gen, 1))
        # TODO: API - it does not seem right to return a list or a device
        #       this non-match should be None
        return matches[0] if matches else []

    def save(self, _id, post, insert=True):
        """
        Save information to the database

        Parameters
        ----------
        _id : str
            ID of device

        post : dict
            Information to place in database

        insert : bool, optional
            Whether or not this a new device to the database

        Raises
        ------
        DuplicateError:
            If insert is True, but there is already a device with the provided
            _id

        SearchError:
            If insert is False, but there is no device with the provided _id

        PermissionError:
            If the write operation fails due to issues with permissions
        """
        with _load_and_store_context(self) as db:
            # New device
            if insert:
                if _id in db.keys():
                    raise DuplicateError("Device {} already exists".format(_id))
                # Add _id keyword
                post.update({'_id': _id})
                # Add to database
                db[_id] = post
            # Updating device
            else:
                # Edit information
                try:
                    db[_id].update(post)
                except KeyError:
                    raise SearchError("No device found {}".format(_id))

    def delete(self, _id):
        """
        Delete a device instance from the database

        Parameters
        ----------
        _id : str
            ID of device

        Raises
        ------
        PermissionError:
            If the write operation fails due to issues with permissions
        """
        with _load_and_store_context(self) as db:
            try:
                db.pop(_id)
            except KeyError:
                logger.warning("Device %s not found in database", _id)
