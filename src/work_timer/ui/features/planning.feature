Feature: Planning

    Scenario: Adding a new planning period
        Given I pressed "a" in the planning view
        When I press "Add" in the opened dialog
        Then a new empty plan for today should be added to the Plan DB

    Scenario: Adding tasks to a plan
        Given I opened a plan
        When I press "a"
        And select a task in the "Add Task" dialog
        Then the task should be added to the plan

    Scenario: Viewing the tasks in a plan
        Given I opened a plan
        Then I should see the tasks in the plan
        And I should see their parents (in a different font)

    # Scenario:
