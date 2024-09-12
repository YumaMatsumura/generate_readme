#!/usr/bin/env python3

# Copyright 2024 Yuma Matsumura All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import subprocess
from openai import OpenAI
from typing import List
from typing import Dict
from typing import Any


# Environment variables
LANGUAGE = os.getenv("LANGUAGE")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
TEMPLATE_PATH = os.getenv("TEMPLATE_PATH")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "README.md")
BRANCH_NAME = os.getenv("BRANCH_NAME", "doc-update")

client = OpenAI(api_key=OPENAI_API_KEY)


def json_to_markdown_table(table_list):
    """
    Converts a list of dictionaries (table data) to a markdown table format.

    :param table_list: List of dictionaries representing table rows
    :return: String in markdown table format
    """
    markdown = ""
    create_table_heading = False
    for table_item in table_list:
        keys = table_item.keys()
        if not create_table_heading:
            markdown = "| " + " | ".join(keys) + " |\n"
            markdown += "| " + " | ".join(["---"] * len(keys)) + " |\n"
        values = [str(table_item[key]) if not isinstance(table_item[key], (dict, list)) else "..." for key in keys]
        markdown += "| " + " | ".join(values) + " |\n"
        create_table_heading = True

    return markdown


def json_to_markdown(json_data):
    """
    Converts JSON data to markdown format.

    :param json_data: Dictionary representing JSON data
    :return: String in markdown format
    """
    markdown = ""
    for key, value in json_data.items():
        if key == "title":
            markdown += f"# {value}\n"
        else:
            if isinstance(value, dict):
                json_to_markdown(value)
            elif isinstance(value, list):
                markdown += f"## {key}\n"
                markdown += "\n"
                markdown += json_to_markdown_table(value)
            else:
                markdown += f"## {key}\n"
                markdown += "\n"
                markdown += f" {value}\n"
        markdown += "\n"
    return markdown


def generate_json(template, commit_diff):
    """
    Generates a JSON response from the commit diff using the OpenAI API based on a given template.

    :param template: JSON schema to format the response
    :param commit_diff: String of the git commit diff
    :return: Parsed JSON response from the OpenAI API
    """
    messages = [
        {"role": "system", "content": f"You are an assistant that extracts information from code and formats it into documentation. Extract the required information from the user's input code following the provided format.Please write in {LANGUAGE}."},
        {"role": "user", "content": commit_diff}
    ]
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "subject_response",
            "strict": True,
            "schema": template
        }
    }
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        response_format=response_format
    )
    content = json.loads(response.choices[0].message.content)
    return content


def generate_readme(template, commit_diff):
    """
    Generates README content in markdown format from the commit diff using a template.

    :param template: JSON schema template
    :param commit_diff: String of the git commit diff
    :return: README content in markdown format
    """
    json_data = generate_json(template, commit_diff)
    markdown = json_to_markdown(json_data)
    return markdown


def get_commit_diff():
    """
    Retrieves the git diff between the latest two commits.

    :return: String containing the git diff output
    :raises: Exception if the git diff command fails
    """
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise Exception("Failed to get git diff.")
    return result.stdout


def check_branch_exists(branch_name):
    """
    Checks if a specific git branch exists.

    :param branch_name: The name of the branch to check
    :return: Boolean indicating if the branch exists
    """
    result = subprocess.run(
        ["git", "branch", "--list", branch_name],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def get_unique_branch_name(base_branch_name):
    """
    Generates a unique branch name by appending a number if the base branch name already exists.

    :param base_branch_name: The base branch name
    :return: Unique branch name
    """
    branch_name = base_branch_name
    counter = 1
    while check_branch_exists(branch_name):
        branch_name = f"{base_branch_name}-{counter}"
        counter += 1
    return branch_name


def set_git_remote_with_token():
    """
    Set Git remote URL with GITHUB_TOKEN for authentication.
    """
    repo_url = f"https://github-actions:{GITHUB_TOKEN}@github.com/{GITHUB_REPOSITORY}"
    subprocess.run(["git", "remote", "set-url", "origin", repo_url], check=True)


def commit_and_push(branch_name, file_path):
    """
    Creates a new branch, commits the generated README.md, and pushes it to the remote repository.

    :param branch_name: The name of the branch to create and push
    :param file_path: Path to the file to be committed
    """
    unique_branch_name = get_unique_branch_name(branch_name)

    # Set Git user as a bot
    subprocess.run(
        ["git", "config", "--local", "user.name", "github-actions[bot]"],
        check=True
    )
    subprocess.run(
        ["git", "config", "--local", "user.email", "github-actions[bot]@users.noreply.github.com"],
        check=True
    )

    # Set Git remote with token for authentication
    set_git_remote_with_token()

    # Checkout new branch
    subprocess.run(
        ["git", "checkout", "-b", unique_branch_name],
        check=True
    )

    # Stage changes and commit
    subprocess.run(
        ["git", "add", file_path],
        check=True
    )
    subprocess.run(
        ["git", "commit", "-m", f"Update {file_path} with latest documentation"],
        check=True
    )

    # Push to remote
    subprocess.run(
        ["git", "push", "origin", unique_branch_name],
        check=True
    )


if __name__ == "__main__":
    try:
        if os.path.exists(OUTPUT_PATH):
            print(f"{OUTPUT_PATH} already exists. Skipping generation.")
        else:
            with open(TEMPLATE_PATH, "r") as f:
                template = json.load(f)

            commit_diff = get_commit_diff()

            readme_content = generate_readme(template, commit_diff)

            with open(OUTPUT_PATH, "w") as f:
                f.write(readme_content)

            commit_and_push(BRANCH_NAME, OUTPUT_PATH)

    except Exception as e:
        print(f"Error: {e}")
