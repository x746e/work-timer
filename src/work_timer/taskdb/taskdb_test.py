"""Tests for work_timer.taskdb."""
import unittest

from work_timer import taskdb
from work_timer.taskdb.task import TaskID, ROOT_TASK_ID, _ROOT_TASK

# TODO: Consider refactoring this file to use .utils.fake_tasks


class TaskTest(unittest.TestCase):

    def test_repr(self):
        new_task = taskdb.Task(title='Hello!', id=TaskID(42))
        self.assertEqual(repr(new_task), '<Task#42: Hello! | new P2 [] @uncommitted>')

        new_task = taskdb.Task(title='Hello one two, ' * 30, id=TaskID(42))
        self.assertEqual(
                repr(new_task),
                '<Task#42: Hello one two, Hello one two, Hello... | new P2 [] @uncommitted>')


class TaskDBTest(unittest.TestCase):

    def setUp(self):
        self.db = taskdb.TaskDB()

    def test_add_task__then_get_it__check_the_title_stays_the_same(self):
        new_task = taskdb.Task(title='Hello!')
        new_task_id = self.db.add(new_task)

        returned_task = self.db.get(new_task_id)
        self.assertEqual(new_task.title, returned_task.title)

    def test_trying_to_set_task_id_raises(self):
        with self.assertRaises(ValueError):
            self.db.add(taskdb.Task(title='I shall raise', id=TaskID(123)))

    def test_changing_returned_task_doesnt_change_the_db(self):
        new_task = taskdb.Task(title='Original Title')
        new_task_id = self.db.add(new_task)

        returned_task = self.db.get(new_task_id)
        returned_task.title = 'New Title'

        another_returned_task = self.db.get(new_task_id)
        self.assertEqual(another_returned_task.title, 'Original Title')

    def test_changing_task_after_adding_doesnt_change_the_db(self):
        new_task = taskdb.Task(title='Original Title')
        new_task_id = self.db.add(new_task)
        new_task.title = 'Changed Title'

        returned_task = self.db.get(new_task_id)
        self.assertEqual(returned_task.title, 'Original Title')

    def test_adding_with_invalid_parent_id_isnt_allowed(self):
        with self.assertRaises(ValueError):
            self.db.add(taskdb.Task(title='Task', parent_id = TaskID(42)))

    def test_update(self):
        new_task = taskdb.Task(title='Original Title')
        new_task_id = self.db.add(new_task)
        returned_task = self.db.get(new_task_id)
        returned_task.title = 'Changed Title'
        self.db.update(returned_task)

        updated_task = self.db.get(new_task_id)
        self.assertEqual(updated_task.title, 'Changed Title')

    def test_update_missing_task_raises(self):
        new_task = taskdb.Task(title='Original Title', id=TaskID(123))
        with self.assertRaises(KeyError):
            self.db.update(new_task)

    def test_update_without_an_id_raises(self):
        new_task = taskdb.Task(title='Original Title')
        with self.assertRaises(ValueError):
            self.db.update(new_task)

    def test_update_with_invalid_parent_id_isnt_allowed(self):
        task_id = self.db.add(taskdb.Task(title='Task A'))
        task = self.db.get(task_id)

        task.parent_id = TaskID(42)
        with self.assertRaises(ValueError):
            self.db.update(task)

    def test_delete(self):
        task = taskdb.Task(title='Original Title')
        task_id = self.db.add(task)

        self.db.delete(task_id)

        with self.assertRaises(KeyError):
            self.db.get(task_id)

    def test_deleting_parents_isnt_allowed(self):
        task_a = taskdb.Task(title='Task A')
        id_a = self.db.add(task_a)
        task_b = taskdb.Task(title='Task B', parent_id=id_a)
        self.db.add(task_b)

        with self.assertRaises(ValueError):
            self.db.delete(id_a)

    def test_get_all(self):
        task_a = taskdb.Task(title='Task A')
        task_b = taskdb.Task(title='Task B')
        id_a = self.db.add(task_a)
        id_b = self.db.add(task_b)

        tasks = self.db.get_all()

        assert {id_a, id_b, ROOT_TASK_ID} == set(tasks.keys())
        assert {task_a.title, task_b.title, _ROOT_TASK.title} == {t.title for t in tasks.values()}

    def test_get_children(self):
        task_a = taskdb.Task(title='Task A')
        id_a = self.db.add(task_a)
        task_b = taskdb.Task(title='Task B', parent_id=id_a)
        self.db.add(task_b)
        task_c = taskdb.Task(title='Task C', parent_id=id_a)
        id_c = self.db.add(task_c)
        task_d = taskdb.Task(title='Task D', parent_id=id_c)
        self.db.add(task_d)

        children = self.db.get_children(parent_id=id_a)

        self.assertCountEqual([task_b.title, task_c.title], [t.title for t in children])

    def test_task_dot_child_ids(self):
        task_a = taskdb.Task(title='Task A')
        id_a = self.db.add(task_a)
        task_b = taskdb.Task(title='Task B', parent_id=id_a)
        id_b = self.db.add(task_b)
        task_c = taskdb.Task(title='Task C', parent_id=id_a)
        id_c = self.db.add(task_c)
        task_d = taskdb.Task(title='Task D', parent_id=id_c)
        self.db.add(task_d)

        # .children doesn't get updated automatically.
        assert task_a.child_ids == []  # pylint: disable=use-implicit-booleaness-not-comparison

        # You need to get the task from the DB again.
        # (While it possible to auto-update all the Task objects on a DB update,
        # that doesn't seem like a great idea: that way you can't be sure if
        # the object your are working with is being concurrently updated at any
        # moment.)
        task_a = self.db.get(id_a)
        assert [id_b, id_c] == task_a.child_ids

    def test_updating_child_ids(self):
        task_a = taskdb.Task(title='Task A')
        id_a = self.db.add(task_a)
        task_b = taskdb.Task(title='Task B', parent_id=id_a)
        id_b = self.db.add(task_b)
        task_c = taskdb.Task(title='Task C', parent_id=id_a)
        id_c = self.db.add(task_c)
        task_d = taskdb.Task(title='Task D', parent_id=id_c)
        id_d = self.db.add(task_d)

        # Before the change: D is a child of C, and not B.
        task_b = self.db.get(id_b)
        assert task_b.child_ids == []
        task_c = self.db.get(id_c)
        assert task_c.child_ids == [id_d]

        # Move D from C to B.
        task_b.child_ids = [id_d]
        self.db.update(task_b)

        # After the change: D is a child of B, and not C.
        task_b = self.db.get(id_b)
        assert task_b.child_ids == [id_d]
        task_c = self.db.get(id_c)
        assert task_c.child_ids == []


if __name__ == '__main__':
    unittest.main()
