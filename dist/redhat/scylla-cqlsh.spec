Name:           %{product}-cqlsh
# cqlsh has its own version numbers (6.x), lower than the scylla versions (2026.x)
# the package had while it was built in scylladb.git: the epoch keeps upgrades working
Epoch:          1
Version:        %{version}
Release:        %{release}%{?dist}
Summary:        cqlsh is a Python-based command-line client for running CQL commands on a cassandra cluster.
Group:          Applications/Databases
Obsoletes:      %{product}-tools < 5.2
Provides:       scylla-enterprise-cqlsh = %{epoch}:%{version}-%{release}
Obsoletes:      scylla-enterprise-cqlsh < 2025.1.0

License:        Apache
URL:            http://www.scylladb.com/
Source0:        %{reloc_pkg}
# the bundled compiled modules are built for the python of one scylla release
# (build_rpm.sh --scylla-release), so only that release's scylla-python3
Requires:       %{product}-python3 >= %{scylla_release}~
Requires:       %{product}-python3 < %{scylla_next_release}~
AutoReqProv:    no
Conflicts:      cassandra

%global debug_package %{nil}
# the bundled .so files (scylla-driver) are also in scylla-python3, their build-id links would conflict
%global _build_id_links none

# no brp-* post-processing at all, it varies by distro (fedora's rewrites the .pyc files)
%global __os_install_post %{nil}


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
/opt/scylladb/share/cassandra/lib


%changelog
* Wed Sep 14 2022 Israel Fruchter <fruch@scylladb.com>
- initial release
