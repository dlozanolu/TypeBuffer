import os
import tempfile

# Must be set before `config` is imported: the module instantiates Config() and
# would otherwise read/write the developer's real ~/.local/share/TypeBuffer.
os.environ.setdefault("TYPEBUFFER_CONFIG_DIR", tempfile.mkdtemp(prefix="typebuffer-tests-"))
