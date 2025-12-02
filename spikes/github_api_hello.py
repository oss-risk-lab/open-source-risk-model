from github import Github

def main():
    token = input("Enter your GitHub token: ").strip()
    g = Github(token)

    # Let's test with a major library
    repo = g.get_repo("numpy/numpy")

    print("\n=== Repository Metadata ===")
    print("Full name:", repo.full_name)
    print("Description:", repo.description)
    print("Stars:", repo.stargazers_count)
    print("Forks:", repo.forks_count)
    print("Open issues:", repo.open_issues_count)
    print("Watchers:", repo.watchers_count)
    print("Last push:", repo.pushed_at)
    print("Created on:", repo.created_at)
    print("Default branch:", repo.default_branch)

    print("\n=== Maintainers (Top 10) ===")
    # print(dir(repo)) to get all possible repo directories
    contributors = repo.get_contributors()[:10]
    for user in contributors:
        print("-", user.login) 

if __name__ == "__main__":
    main()
