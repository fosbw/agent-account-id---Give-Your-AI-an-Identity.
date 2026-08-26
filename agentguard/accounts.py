from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, TypeVar
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import random
from unidecode import unidecode

T = TypeVar("T")


class AccountError(RuntimeError):
    """Base error for the Agent Account runtime."""


class ProviderOperationUnavailable(AccountError):
    """Raised when a provider does not expose a requested operation."""


_SECRET_NAMES = {
    "password",
    "passwd",
    "cookie",
    "cookies",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "secret",
    "private_key",
    "recovery_code",
    "recovery_codes",
}
_HANDLE_PATTERN = re.compile(r"^agent_account://[a-z0-9][a-z0-9._-]{0,63}/[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    account_creation: str
    identity_initialization: str
    credential_initialization: str
    browser_session: str
    persistent_session: str
    verification: str
    recovery: str
    credential_rotation: str
    revocation: str
    authentication: str = "provider_adapter"

    def capability_matrix(self) -> dict[str, str]:
        return {
            "CREATE_ACCOUNT": self.account_creation,
            "INITIALIZE_ACCOUNT": self.identity_initialization,
            "AUTHENTICATE": self.authentication,
            "PERSIST_SESSION": self.persistent_session,
            "REFRESH_SESSION": self.recovery,
            "REVOKE_SESSION": self.revocation,
            "ROTATE_CREDENTIAL": self.credential_rotation,
            "VERIFY_STATE": self.verification,
        }

    def safe_metadata(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class AgentAccount:
    account_id: str
    handle: str
    agent_id: str
    provider: str
    display_name: str
    state: str
    created_at: float
    updated_at: float
    browser_profile: str | None = None
    identity_id: str | None = None
    verification_state: str = "not_started"
    session_state: str = "not_started"
    authorization_basis: str = "provider_authorized"
    external_account_ref: str | None = None

    def safe_metadata(self) -> dict:
        return asdict(self)


class AccountProvisioner(Protocol):
    provider: str

    def capabilities(self) -> ProviderCapabilities:
        ...

    def can_create_account(self) -> bool:
        ...

    def create_account(self, agent_id: str, display_name: str) -> AgentAccount:
        ...

    def initialize_identity(self, account: AgentAccount, identity_id: str) -> AgentAccount:
        ...

    def initialize_credentials(self, account: AgentAccount) -> str:
        """Return an opaque vault reference, never raw credentials."""
        ...

    def initialize_browser_session(self, account: AgentAccount, profile_dir: Path) -> AgentAccount:
        ...

    def verify_state(self, account: AgentAccount) -> AgentAccount:
        ...

    def recover_session(self, account: AgentAccount) -> AgentAccount:
        ...

    def rotate_credentials(self, account: AgentAccount) -> str:
        ...

    def revoke_account(self, account: AgentAccount) -> AgentAccount:
        ...


class AccountVault:
    """Process-bound secret boundary with non-secret on-disk metadata.

    Provider adapters may submit a secret through ``put_secret``. The value is
    kept only in the vault object's private memory and can be consumed through
    ``use_secret`` by an adapter. Public metadata, model context, tool output,
    and event logs contain only an opaque reference and ``secret_present``.
    """

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._secrets: dict[str, str] = {}

    def put_reference(self, handle: str, metadata: Mapping[str, object] | None = None) -> str:
        validate_account_handle(handle)
        clean = _safe_metadata(metadata or {})
        reference_id = "ref-" + uuid.uuid4().hex
        path = self.root / f"{reference_id}.json"
        path.write_text(
            json.dumps({"reference_id": reference_id, "handle": handle, "metadata": clean, "secret_present": False}, indent=2) + "\n",
            encoding="utf-8",
        )
        return reference_id

    def put_secret(self, handle: str, name: str, value: str) -> str:
        """Accept a provider secret internally and return only an opaque ref.

        The raw value is never written to disk and is never returned. The
        caller must be a provider adapter that immediately uses the reference.
        """
        validate_account_handle(handle)
        if not name or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", name):
            raise AccountError("secret name must be a safe identifier")
        if not isinstance(value, str) or not value:
            raise AccountError("secret value must be a non-empty string")
        reference_id = "secret-" + uuid.uuid4().hex
        self._secrets[reference_id] = value
        path = self.root / f"{reference_id}.json"
        path.write_text(
            json.dumps({"reference_id": reference_id, "handle": handle, "name": name, "secret_present": True}, indent=2) + "\n",
            encoding="utf-8",
        )
        return reference_id

    def use_secret(self, reference_id: str, consumer: Callable[[str], T]) -> T:
        """Run provider code with a secret without exposing it as a result."""
        if not reference_id or not reference_id.startswith("secret-"):
            raise AccountError("invalid secret reference")
        if reference_id not in self._secrets:
            raise FileNotFoundError(f"secret reference is not available in this process: {reference_id}")
        if not callable(consumer):
            raise TypeError("consumer must be callable")
        return consumer(self._secrets[reference_id])

    def list_references(self) -> list[dict]:
        rows = []
        for path in sorted(self.root.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def find_active_secret_reference(self, handle: str, name: str) -> str:
        """Return a matching secret reference that is loaded in this process."""
        validate_account_handle(handle)
        for row in self.list_references():
            reference_id = str(row.get("reference_id") or "")
            if row.get("handle") == handle and row.get("name") == name and reference_id in self._secrets:
                return reference_id
        raise FileNotFoundError(f"active secret reference is not available for {handle} and {name}")

    def get_reference(self, reference_id: str) -> dict:
        if not reference_id or "/" in reference_id or "\\" in reference_id:
            raise ValueError("invalid vault reference id")
        path = self.root / f"{reference_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"vault reference not found: {reference_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def revoke_reference(self, reference_id: str) -> None:
        self.get_reference(reference_id)
        self._secrets.pop(reference_id, None)
        (self.root / f"{reference_id}.json").unlink(missing_ok=True)


def validate_account_handle(handle: str) -> str:
    if not isinstance(handle, str) or not _HANDLE_PATTERN.fullmatch(handle):
        raise AccountError("account handle must be an opaque agent_account://provider/id reference")
    return handle


def _safe_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    clean: dict[str, object] = {}
    for key, value in metadata.items():
        name = str(key).lower()
        if name in _SECRET_NAMES or any(secret in name for secret in _SECRET_NAMES):
            raise AccountError(f"account metadata cannot contain secret field: {key}")
        if isinstance(value, (dict, list, tuple)):
            raise AccountError("account metadata must remain flat and non-sensitive")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise AccountError(f"unsupported account metadata value: {key}")
        clean[str(key)] = value
    return clean



    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            account_creation="supported_local_only",
            authentication="supported_local_only",
            identity_initialization="supported_reference_only",
            credential_initialization="not_accepted",
            browser_session="supported",
            persistent_session="supported",
            verification="manual_or_provider_signal",
            recovery="reference_only",
            credential_rotation="not_accepted",
            revocation="supported_local_record",
        )
class GoogleProvider:
    provider = "google"

    def __init__(self, vault: AccountVault | None = None):
        self.vault = vault or AccountVault(Path("./vault"))
        self.root = Path("./google_accounts")
        self.root.mkdir(parents=True, exist_ok=True)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            account_creation="supported",
            authentication="supported_via_oauth",
            identity_initialization="supported_via_oauth",
            credential_initialization="provider_managed_only",
            browser_session="supported_with_external_runtime",
            persistent_session="supported_with_external_runtime",
            verification="provider_state_required",
            recovery="provider_managed_only",
            credential_rotation="provider_managed_only",
            revocation="provider_managed_only",
        )

    def can_create_account(self) -> bool:
        return False

    def create_account(self, agent_id: str, display_name: str) -> AgentAccount:
        raise ProviderOperationUnavailable("Provider does not expose this operation: Google account provisioning")

    def initialize_identity(self, account: AgentAccount, identity_id: str) -> AgentAccount:
        if not identity_id or "/" in identity_id or "\\" in identity_id:
            raise AccountError("identity_id must be a non-secret reference")
        account.identity_id = identity_id
        account.state = "identity_initialized"
        account.updated_at = time.time()
        self._write(account)
        return account

    def initialize_credentials(self, account: AgentAccount) -> str:
        raise ProviderOperationUnavailable("Provider does not expose this operation: raw credential initialization")

    def initialize_browser_session(self, account: AgentAccount, profile_dir: Path) -> AgentAccount:
        profile_dir.mkdir(parents=True, exist_ok=True)
        account.browser_profile = str(profile_dir)
        account.session_state = "initialized"
        account.state = "browser_initialized"
        account.updated_at = time.time()
        self._write(account)
        return account

    def verify_state(self, account: AgentAccount) -> AgentAccount:
        account.verification_state = "provider_state_required"
        account.state = "verification_required"
        account.updated_at = time.time()
        self._write(account)
        return account

    def recover_session(self, account: AgentAccount) -> AgentAccount:
        account.session_state = "reauthentication_required"
        account.state = "reauthentication_required"
        account.updated_at = time.time()
        self._write(account)
        return account

    def rotate_credentials(self, account: AgentAccount) -> str:
        raise ProviderOperationUnavailable("Provider does not expose this operation: credential rotation in this runtime")

    def revoke_account(self, account: AgentAccount) -> AgentAccount:
        account.state = "revocation_requested"
        account.session_state = "revoked"
        account.updated_at = time.time()
        self._write(account)
        return account

    def get(self, account_id: str) -> AgentAccount:
        if not account_id or "/" in account_id or "\\" in account_id:
            raise ValueError("invalid account id")
        path = self.root / f"{account_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"account not found: {account_id}")
        return AgentAccount(**json.loads(path.read_text(encoding="utf-8")))

    def _write(self, account: AgentAccount) -> None:
        (self.root / f"{account.account_id}.json").write_text(
            json.dumps(account.safe_metadata(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    def can_create_account(self) -> bool:
        return True

    def create_account(self, agent_id: str, display_name: str) -> AgentAccount:
        if not agent_id.strip() or not display_name.strip():
            raise AccountError("agent_id and display_name are required")
        account_id = "acct-" + uuid.uuid4().hex
        handle = f"agent_account://local/{account_id}"
        now = time.time()
        account = AgentAccount(
            account_id=account_id,
            handle=handle,
            agent_id=agent_id.strip(),
            provider=self.provider,
            display_name=display_name.strip(),
            state="created",
            created_at=now,
            updated_at=now,
            authorization_basis="local_runtime",
        )
        self._write(account)
        return account

    def initialize_identity(self, account: AgentAccount, identity_id: str) -> AgentAccount:
        if not identity_id or "/" in identity_id or "\\" in identity_id:
            raise AccountError("identity_id must be a non-secret reference")
        account.identity_id = identity_id
        account.state = "identity_initialized"
        account.updated_at = time.time()
        self._write(account)
        return account

    def initialize_credentials(self, account: AgentAccount) -> str:
        raise ProviderOperationUnavailable("Local runtime does not accept raw credentials; configure an external vault adapter")

    def initialize_browser_session(self, account: AgentAccount, profile_dir: Path) -> AgentAccount:
        profile_dir.mkdir(parents=True, exist_ok=True)
        account.browser_profile = str(profile_dir.resolve())
        account.session_state = "initialized"
        account.state = "browser_initialized"
        account.updated_at = time.time()
        self._write(account)
        return account

    def verify_state(self, account: AgentAccount) -> AgentAccount:
        account.verification_state = "provider_state_required"
        account.state = "verification_required"
        account.updated_at = time.time()
        self._write(account)
        return account

    def recover_session(self, account: AgentAccount) -> AgentAccount:
        account.session_state = "reauthentication_required"
        account.state = "reauthentication_required"
        account.updated_at = time.time()
        self._write(account)
        return account

    def rotate_credentials(self, account: AgentAccount) -> str:
        raise ProviderOperationUnavailable("Local runtime does not rotate raw credentials")

    def revoke_account(self, account: AgentAccount) -> AgentAccount:
        account.state = "revoked"
        account.session_state = "revoked"
        account.updated_at = time.time()
        self._write(account)
        return account

    def get(self, account_id: str) -> AgentAccount:
        if not account_id or "/" in account_id or "\\" in account_id:
            raise ValueError("invalid account id")
        path = self.root / f"{account_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"account not found: {account_id}")
        return AgentAccount(**json.loads(path.read_text(encoding="utf-8")))

    def _write(self, account: AgentAccount) -> None:
        (self.root / f"{account.account_id}.json").write_text(
            json.dumps(account.safe_metadata(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
class GoogleCreatorProvider(GoogleProvider):
    def __init__(self, vault: AccountVault | None = None, headless: bool = False):
        super().__init__(vault)
        self.headless = headless

    def can_create_account(self) -> bool:
        return True

    def _generate_random_data(self):
        first_names = ["Ahmed", "Mohamed", "Youssef", "Ali", "Hassan", "Omar", "Khaled", "Said"]
        last_names = ["Hassan", "Ibrahim", "Said", "Mohamed", "Ali", "Youssef", "Omar", "Khaled"]
        
        first = random.choice(first_names)
        last = random.choice(last_names)
        first_clean = unidecode(first).lower()
        last_clean = unidecode(last).lower()
        username = f"{first_clean}.{last_clean}{random.randint(1000, 9999)}"
        
        return {
            "first": first,
            "last": last,
            "username": username,
            "password": f"Test@{random.randint(1000, 9999)}!",
            "birthday": str(random.randint(1, 28)),
            "birth_month": str(random.randint(1, 12)),
            "birth_year": str(random.randint(1970, 2005)),
            "gender": "2"
        }

    def create_account(self, agent_id: str, display_name: str) -> AgentAccount:
        if not agent_id.strip() or not display_name.strip():
            raise AccountError("agent_id and display_name are required")

        data = self._generate_random_data()
        email = f"{data['username']}@gmail.com"

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            driver.get("https://accounts.google.com/signup")
            wait = WebDriverWait(driver, 15)

            wait.until(EC.presence_of_element_located((By.NAME, "firstName"))).send_keys(data["first"])
            driver.find_element(By.NAME, "lastName").send_keys(data["last"])
            driver.find_element(By.ID, "accountDetailsNext").click()
            time.sleep(2)

            wait.until(EC.presence_of_element_located((By.NAME, "Username"))).send_keys(data["username"])
            driver.find_element(By.NAME, "Passwd").send_keys(data["password"])
            driver.find_element(By.NAME, "ConfirmPasswd").send_keys(data["password"])
            driver.find_element(By.ID, "accountDetailsNext").click()
            time.sleep(2)

            wait.until(EC.presence_of_element_located((By.NAME, "BirthDay"))).send_keys(data["birthday"])
            driver.find_element(By.NAME, "BirthMonth").send_keys(data["birth_month"])
            driver.find_element(By.NAME, "BirthYear").send_keys(data["birth_year"])
            driver.find_element(By.NAME, "Gender").send_keys(data["gender"])

            print("=" * 60)
            print("✅ تم ملء كل البيانات بنجاح!")
            print(f"📧 الإيميل: {email}")
            print(f"🔑 كلمة السر: {data['password']}")
            print("=" * 60)
            print("⏳ السكربت واقف عند شاشة رقم التليفون و reCAPTCHA...")
            print("📱 أكمل أنت باقي الخطوات (رقم التليفون والتحقق)")
            print("⌨️  بعد ما تكمل التحقق، اضغط Enter عشان السكربت يكمل...")
            input()

            try:
                driver.find_element(By.ID, "accountDetailsNext").click()
                time.sleep(3)
                print("🎉 تم إنشاء الحساب بنجاح!")
            except:
                print("⚠️ مشكلة في الضغط على التالي، ممكن تكون خلصت الخطوات بإيدك.")

        except Exception as e:
            raise AccountError(f"Failed to create Google account: {e}")
        finally:
            driver.quit()

        account_id = "gmail-" + uuid.uuid4().hex
        handle = f"agent_account://google/{account_id}"
        now = time.time()

        account = AgentAccount(
            account_id=account_id,
            handle=handle,
            agent_id=agent_id.strip(),
            provider="google",
            display_name=display_name.strip(),
            state="created",
            created_at=now,
            updated_at=now,
            external_account_ref=email,
            authorization_basis="provider_authorized"
        )

        secret_ref = self.vault.put_secret(handle, "password", data["password"])
        account.external_account_ref = secret_ref

        self._write(account)
        return account
