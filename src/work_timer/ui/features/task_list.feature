@slow
Feature: Task List
    A list with tasks

    Scenario: Creating a new task should expand the parent
        Given I opened a task list
        When I add a child task to a leaf node
        Then the parent node should get expanded

    Scenario: Moving a task into parent should expand the parent
        Given I opened a task list
        When I reparent a task into a leaf node
        Then the parent node should get expanded
