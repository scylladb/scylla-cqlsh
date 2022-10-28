Name: %{name}
Version: %{version}
Release: %{release}
Summary: cqlsh is a Python-based command-line client for running CQL commands on a cassandra cluster.
AutoReqProv: no
Provides: %{name}

License: Apache
Source0: %{reloc_pkg}

%global __brp_python_bytecompile %{nil}
%global __brp_mangle_shebangs %{nil}
%global __brp_ldconfig %{nil}
%global __brp_strip %{nil}
%global __brp_strip_comment_note %{nil}
%global __brp_strip_static_archive %{nil}

%description
cqlsh is a Python-based command-line client for running CQL commands on a cassandra cluster.

%prep
%setup -q -n scylla-cqlsh

%install
./install.sh --root "$RPM_BUILD_ROOT"

%files
%dir %{target}
%{target}/*
%if %{defined has_bindir}
%{_bindir}/*
%endif

%changelog

