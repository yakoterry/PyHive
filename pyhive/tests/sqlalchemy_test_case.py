# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from builtins import object
from distutils.version import StrictVersion
from future.utils import with_metaclass
import sqlalchemy
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.schema import Index
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import Table
from sqlalchemy.sql import expression
import abc
import contextlib
import functools
import unittest


def with_engine_connection(fn):
    """Pass a connection to the given function and handle cleanup.

    The connection is taken from ``self.create_engine()``.
    """
    @functools.wraps(fn)
    def wrapped_fn(self, *args, **kwargs):
        engine = self.create_engine()
        try:
            with contextlib.closing(engine.connect()) as connection:
                fn(self, engine, connection, *args, **kwargs)
        finally:
            engine.dispose()
    return wrapped_fn


class SqlAlchemyTestCase(with_metaclass(abc.ABCMeta, object)):
    @with_engine_connection
    def test_basic_query(self, engine, connection):
        rows = connection.execute('SELECT * FROM one_row').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].number_of_rows, 1)  # number_of_rows is the column name
        self.assertEqual(len(rows[0]), 1)

    @with_engine_connection
    def test_one_row_complex_null(self, engine, connection):
        one_row_complex_null = Table('one_row_complex_null', MetaData(bind=engine), autoload=True)
        rows = one_row_complex_null.select().execute().fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(list(rows[0]), [None] * len(rows[0]))

    @with_engine_connection
    def test_reflect_no_such_table(self, engine, connection):
        """reflecttable should throw an exception on an invalid table"""
        self.assertRaises(
            NoSuchTableError,
            lambda: Table('this_does_not_exist', MetaData(bind=engine), autoload=True))
        self.assertRaises(
            NoSuchTableError,
            lambda: Table('this_does_not_exist', MetaData(bind=engine),
                          schema='also_does_not_exist', autoload=True))

    @with_engine_connection
    def test_reflect_include_columns(self, engine, connection):
        """When passed include_columns, reflecttable should filter out other columns"""
        one_row_complex = Table('one_row_complex', MetaData(bind=engine))
        engine.dialect.reflecttable(
            connection, one_row_complex, include_columns=['int'], exclude_columns=[])
        self.assertEqual(len(one_row_complex.c), 1)
        self.assertIsNotNone(one_row_complex.c.int)
        self.assertRaises(AttributeError, lambda: one_row_complex.c.tinyint)

    @with_engine_connection
    def test_reflect_with_schema(self, engine, connection):
        dummy = Table('dummy_table', MetaData(bind=engine), schema='pyhive_test_database',
                      autoload=True)
        self.assertEqual(len(dummy.c), 1)
        self.assertIsNotNone(dummy.c.a)

    @with_engine_connection
    def test_reflect_partitions(self, engine, connection):
        """reflecttable should get the partition column as an index"""
        many_rows = Table('many_rows', MetaData(bind=engine), autoload=True)
        self.assertEqual(len(many_rows.c), 2)
        self.assertEqual(repr(many_rows.indexes), repr({Index('partition', many_rows.c.b)}))

        many_rows = Table('many_rows', MetaData(bind=engine))
        engine.dialect.reflecttable(
            connection, many_rows, include_columns=['a'], exclude_columns=[])
        self.assertEqual(len(many_rows.c), 1)
        self.assertFalse(many_rows.c.a.index)
        self.assertFalse(many_rows.indexes)

        many_rows = Table('many_rows', MetaData(bind=engine))
        engine.dialect.reflecttable(
            connection, many_rows, include_columns=['b'], exclude_columns=[])
        self.assertEqual(len(many_rows.c), 1)
        self.assertEqual(repr(many_rows.indexes), repr({Index('partition', many_rows.c.b)}))

    @with_engine_connection
    def test_unicode(self, engine, connection):
        """Verify that unicode strings make it through SQLAlchemy and the backend"""
        unicode_str = "白人看不懂"
        one_row = Table('one_row', MetaData(bind=engine))
        returned_str = sqlalchemy.select(
            [expression.bindparam("好", unicode_str)],
            from_obj=one_row,
        ).scalar()
        self.assertEqual(returned_str, unicode_str)

    @unittest.skipIf(StrictVersion(sqlalchemy.__version__) < StrictVersion('0.8.0'),
                     "inspect not available yet")
    @with_engine_connection
    def test_reflect_schemas(self, engine, connection):
        insp = sqlalchemy.inspect(engine)
        schemas = insp.get_schema_names()
        self.assertIn('pyhive_test_database', schemas)
        self.assertIn('default', schemas)

    @unittest.skipIf(StrictVersion(sqlalchemy.__version__) < StrictVersion('0.8.0'),
                     "inspect not available yet")
    @with_engine_connection
    def test_get_table_names(self, engine, connection):
        meta = MetaData()
        meta.reflect(bind=engine)
        self.assertIn('one_row', meta.tables)
        self.assertIn('one_row_complex', meta.tables)

        insp = sqlalchemy.inspect(engine)
        self.assertIn(
            'dummy_table',
            insp.get_table_names(schema='pyhive_test_database'),
        )

    @with_engine_connection
    def test_has_table(self, engine, connection):
        self.assertTrue(Table('one_row', MetaData(bind=engine)).exists())
        self.assertFalse(Table('this_table_does_not_exist', MetaData(bind=engine)).exists())

    @unittest.skipIf(StrictVersion(sqlalchemy.__version__) < StrictVersion('0.6.0'),
                     "visitor stuff for changing char_length -> length not available yet")
    @with_engine_connection
    def test_char_length(self, engine, connection):
        one_row_complex = Table('one_row_complex', MetaData(bind=engine), autoload=True)
        result = sqlalchemy.select([
            sqlalchemy.func.char_length(one_row_complex.c.string)
        ]).execute().scalar()
        self.assertEqual(result, len('a string'))
