import unittest

import taskdb


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
            self.db.add(taskdb.Task(title='I shall raise', id=123))

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

    def test_update(self):
        new_task = taskdb.Task(title='Original Title')
        new_task_id = self.db.add(new_task)
        returned_task = self.db.get(new_task_id)
        returned_task.title = 'Changed Title'
        self.db.update(returned_task)

        updated_task = self.db.get(new_task_id)
        self.assertEqual(updated_task.title, 'Changed Title')

    def test_update_missing_task_raises(self):
        new_task = taskdb.Task(title='Original Title', id=123)
        with self.assertRaises(KeyError):
            self.db.update(new_task)

    def test_update_without_an_id_raises(self):
        new_task = taskdb.Task(title='Original Title')
        with self.assertRaises(ValueError):
            self.db.update(new_task)

    def test_get_all(self):
        task_a = taskdb.Task(title='Task A')
        task_b = taskdb.Task(title='Task B')
        id_a = self.db.add(task_a)
        id_b = self.db.add(task_b)

        tasks = self.db.get_all()

        self.assertCountEqual([id_a, id_b], tasks.keys())
        self.assertCountEqual([task_a.title, task_b.title], [t.title for t in tasks.values()])
