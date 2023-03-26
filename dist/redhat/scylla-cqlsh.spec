Name:           %{product}-cqlsh
Version:        %{version}
Release:        %{release}%{?dist}
Summary:        cqlsh is a Python-based command-line client for running CQL commands on a cassandra cluster.
Group:          Applications/Databases
Obsoletes:      %{product}-tools < 5.2

License:        Apache
URL:            http://www.scylladb.com/
Source0:        %{reloc_pkg}
BuildArch:      noarch
Requires:       python3
AutoReqProv:    no
Conflicts:      cassandra

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


%build

%install
rm -rf $RPM_BUILD_ROOT
./install.sh --root "$RPM_BUILD_ROOT"

%files
%{_bindir}/cqlsh
%{_bindir}/cqlsh.py
/opt/scylladb/share/cassandra/bin/*
/opt/scylladb/share/cassandra/libexec/*
/opt/scylladb/share/cassandra/pylib/*
/opt/scylladb/share/cassandra/lib/*


%changelog
* Wed Sep 14 2022 Israel Fruchter <fruch@scylladb.com>
- initial release
