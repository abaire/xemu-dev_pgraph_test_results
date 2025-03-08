xemu-dev_pgraph_test_results
===

** WARNING: YOU PROBABLY WANT [xemu-nxdk_pgraph_tests_results](https://github.com/abaire/xemu-nxdk_pgraph_tests_results) rather than this repo **

This repo is solely intended to showcase test results for pull requests of [xemu](http://xemu.app).

[Results are browsable on this repo's Pages page](https://abaire.github.io/xemu-dev_pgraph_test_results)

[Results are also browsable in the wiki](https://github.com/abaire/xemu-dev_pgraph_test_results/wiki)

## Usage for xemu contributors

If you are doing xemu development:

1. Fork this repository
2. Create a new branch in this repository (ideally matching the branch name of your xemu work, for clarity).
3. Use `execute.py` to run the [nxdk_pgraph_tests](https://github.com/abaire/nxdk_pgraph_tests) against your development xemu build.
4. Examine the results and commit them if they look correct.
5. Push the new results branch to this repository and create a PR. The GitHub action will compare the results to [hardware golden results](https://github.com/abaire/nxdk_pgraph_tests_golden_results) and the best known [xemu results](https://github.com/abaire/xemu-nxdk_pgraph_tests_results). It will add them to [the wiki](https://github.com/abaire/xemu-dev_pgraph_test_results/wiki) as a new page matching the branch name.

You can then add a link to the wiki to your xemu PR.

[This generate_xemu_dev_pgraph_test_results_branch.sh script](https://github.com/abaire/xemu-util-scripts/blob/5c676ac2f1cfd7cb9420cb815919f8875fda067c/generate_xemu_dev_pgraph_test_results_branch.sh) automates some of this work and may be cloned or extended to support different workspace layouts.

