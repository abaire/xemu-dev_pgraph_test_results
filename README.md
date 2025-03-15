xemu-dev_pgraph_test_results
===

** WARNING: YOU PROBABLY WANT [xemu-nxdk_pgraph_tests_results](https://github.com/abaire/xemu-nxdk_pgraph_tests_results) rather than this repo **

This repo is solely intended to showcase test results for pull requests of [xemu](http://xemu.app).

[Results are browsable on this repo's Pages page](https://abaire.github.io/xemu-dev_pgraph_test_results)

## Usage for xemu contributors

If you are doing xemu development:

### One time setup
1. Create a new instance of this template repository (click the "Use this template" button)
2. Go to the `Settings` for your repository and change the `Pages` "Build and deployment" setting to `GitHub Actions`. https://github.com/<your_user>/xemu-dev_pgraph_test_results/settings/pages
3. Edit the README.md file and update the "Results are browsable..." links just above to point at your repo instead of the template repo (generally just change `abaire` to your username).
4. Run `pip install -r requirements.txt` from within the repo to install packages needed to run the tester. You will need at least Python 3.10.
5. Go through the below steps for the first PR. The "Deploy site" step will fail with something like `not allowed to deploy to github-pages due to environment protection rules.`
6. Go to `Settings` `Environments` and edit the `github-pages` environment. Change `Deployment branches and tags` from `Selected branches and tags` to `No restriction`
7. Go back to the failed action via `Actions` in the top bar and "Re-run failed jobs"

### For each xemu PR
1. Create a new branch in your repository, ideally matching the branch name of your xemu work, for clarity.
2. Use `execute.py` to run the [nxdk_pgraph_tests](https://github.com/abaire/nxdk_pgraph_tests) against your development xemu build.
3. Examine the results and commit them to your new branch if they look correct.
4. Push the new results branch to your repository and create a PR. The associated GitHub action will compare the results to [hardware golden results](https://github.com/abaire/nxdk_pgraph_tests_golden_results) and the best known [xemu results](https://github.com/abaire/xemu-nxdk_pgraph_tests_results). Then will add the diffs to the GitHub Pages page for your repo as a new page matching the branch name.

You can then add a link to that results page to your xemu PR.

[This generate_xemu_dev_pgraph_test_results_branch.sh script](https://github.com/abaire/xemu-util-scripts/blob/5c676ac2f1cfd7cb9420cb815919f8875fda067c/generate_xemu_dev_pgraph_test_results_branch.sh) automates some of this work and may be cloned or extended to support different workspace layouts.

