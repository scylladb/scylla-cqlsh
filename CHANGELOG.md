## v6.1.1-scylla

* cqlsh: add --safe-mode confirmation for DROP/TRUNCATE (ade2fbb)
* ci: automate releases with a rolling release PR (af88f59)
* chore(deps): update softprops/action-gh-release action to v3.0.4 (23a37a1)
* chore(deps): update scylladb/github-automation digest to 575136a (a48a2df)
* chore(deps): update docker/login-action action to v4.8.0 (7bfeb73)
* ci: run the Windows and macOS jobs on PRs only when labeled (c669bb4)
* cqlsh: complete the indexed column, not the raw index target (2ce6368)
* pylexotron: raise on a bad grammar literal instead of printing (ddaa01b)
* authproviderhandling: accept duck-typed auth providers (456bfbc)
* copyutil: remove dead strace helper (160d1a8)
* fix: ensure file handle is closed in do_source using try/finally (3389968)
* fix: use context manager for file handle in get_file_encoding_bomsize (4259444)
* security: validate auth provider is a subclass of AuthProvider (4252bd5)
* security: replace eval() with ast.literal_eval() in pylexotron.py (d5f5135)
* security: remove shell=True from subprocess.call in do_clear (c3bcd20)
* security: replace os.system() with subprocess.Popen() in copyutil.py (756e57c)

