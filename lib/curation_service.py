"""
lib/curation_service.py - Servicio de Persistencia y Curación Human-in-the-Loop
Gestiona la base de datos SQLite curation_hub.db:
- Claims y Disclaims de publicaciones.
- Carga de obras personalizadas (.bib manual / no indizadas).
- Roles de usuario (investigador, admin_institucional, super_admin) y solicitudes de acreditación.
- Almacenamiento cifrado (Fernet) de tokens OAuth para la API de escritura de ORCID.
"""

import os
import re
import sqlite3
import base64
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv("/home/sinapsisai/.env")

DB_DIR = "/home/sinapsisai/data"
DB_PATH = os.path.join(DB_DIR, "curation_hub.db")

def _get_encryption_key() -> bytes:
    """Obtiene o deriva una clave Fernet válida de 32 bytes en base64 para encriptar tokens."""
    raw_key = os.getenv("ORCID_TOKEN_ENCRYPTION_KEY") or os.getenv("APP_SECRET_KEY") or "sinapsisai_orcid_secret_salt_2026"
    key_bytes = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)

def encrypt_token(plain_token: str) -> str:
    """Cifra un token sensible usando Fernet."""
    if not plain_token:
        return ""
    f = Fernet(_get_encryption_key())
    return f.encrypt(plain_token.encode('utf-8')).decode('utf-8')

def decrypt_token(cipher_token: str) -> str:
    """Descifra un token encriptado."""
    if not cipher_token:
        return ""
    f = Fernet(_get_encryption_key())
    try:
        return f.decrypt(cipher_token.encode('utf-8')).decode('utf-8')
    except Exception as e:
        print(f"[curation_service] Error descifrando token: {e}")
        return ""

def init_db():
    """Inicializa el esquema relacional en SQLite."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_roles (
        orcid TEXT PRIMARY KEY,
        name TEXT,
        email TEXT,
        institution TEXT,
        dependency TEXT,
        role TEXT DEFAULT 'researcher',
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_by TEXT,
        approved_at TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_claimed_works (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orcid TEXT NOT NULL,
        work_id TEXT NOT NULL,
        source TEXT DEFAULT 'openalex',
        claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(orcid, work_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_disclaimed_works (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orcid TEXT NOT NULL,
        work_id TEXT NOT NULL,
        title TEXT,
        reason TEXT,
        disclaimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(orcid, work_id)
    );
    """)
    try:
        cur.execute("ALTER TABLE user_disclaimed_works ADD COLUMN title TEXT")
    except Exception:
        pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_custom_works (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        orcid TEXT NOT NULL,
        doi TEXT,
        title TEXT NOT NULL,
        authors TEXT,
        journal TEXT,
        year INTEGER,
        volume TEXT,
        issue TEXT,
        pages TEXT,
        bibtex_raw TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_tokens (
        orcid TEXT PRIMARY KEY,
        encrypted_token TEXT NOT NULL,
        token_type TEXT DEFAULT 'bearer',
        scope TEXT,
        expires_at TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS institutional_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_entity TEXT NOT NULL,
        alias TEXT NOT NULL,
        created_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(canonical_entity, alias)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS hidden_profiles (
        orcid TEXT PRIMARY KEY,
        academic_id TEXT,
        academic_name TEXT,
        hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reason TEXT
    );
    """)

    conn.commit()
    conn.close()

# Auto-inicializar al importar
init_db()

# ── Funciones de Claims & Disclaims ──

def claim_work(orcid: str, work_id: str, source: str = "openalex") -> bool:
    """Registra que un artículo sí pertenece al autor."""
    if not orcid or not work_id:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT OR REPLACE INTO user_claimed_works (orcid, work_id, source) VALUES (?, ?, ?)",
            (clean_orc, work_id.strip(), source)
        )
        # Si estaba en disclaimed, removerlo
        cur.execute(
            "DELETE FROM user_disclaimed_works WHERE orcid = ? AND work_id = ?",
            (clean_orc, work_id.strip())
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error en claim_work: {e}")
        return False
    finally:
        conn.close()

def disclaim_work(orcid: str, work_id: str, title: str = "", reason: str = "") -> bool:
    """Registra que un artículo NO pertenece al autor (falso positivo)."""
    if not orcid or not work_id:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT OR REPLACE INTO user_disclaimed_works (orcid, work_id, title, reason) VALUES (?, ?, ?, ?)",
            (clean_orc, work_id.strip(), title.strip(), reason)
        )
        # Si estaba en claimed, removerlo
        cur.execute(
            "DELETE FROM user_claimed_works WHERE orcid = ? AND work_id = ?",
            (clean_orc, work_id.strip())
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error en disclaim_work: {e}")
        return False
    finally:
        conn.close()

def get_disclaimed_work_ids(orcid: str) -> List[str]:
    """Retorna los IDs de obras que el usuario ha descartado."""
    if not orcid:
        return []
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT work_id FROM user_disclaimed_works WHERE orcid = ?", (clean_orc,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_claimed_work_ids(orcid: str) -> List[str]:
    """Retorna los IDs de obras que el usuario ha reclamado explícitamente."""
    if not orcid:
        return []
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT work_id FROM user_claimed_works WHERE orcid = ?", (clean_orc,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

# ── Obras Personalizadas (.bib subido por el autor) ──

def add_custom_work(orcid: str, title: str, authors: str = "", journal: str = "", year: Optional[int] = None, doi: str = "", volume: str = "", issue: str = "", pages: str = "", bibtex_raw: str = "") -> bool:
    """Añade una obra manual cargada por el autor a su perfil."""
    if not orcid or not title:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO user_custom_works (orcid, doi, title, authors, journal, year, volume, issue, pages, bibtex_raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (clean_orc, doi, title, authors, journal, year, volume, issue, pages, bibtex_raw))
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error en add_custom_work: {e}")
        return False
    finally:
        conn.close()

def get_custom_works(orcid: str) -> List[Dict[str, Any]]:
    """Retorna las obras manuales registradas por el usuario."""
    if not orcid:
        return []
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, doi, title, authors, journal, year, volume, issue, pages, bibtex_raw, created_at FROM user_custom_works WHERE orcid = ?", (clean_orc,))
    rows = cur.fetchall()
    conn.close()
    return [{
        "id": r[0], "doi": r[1], "title": r[2], "authors": r[3], "journal": r[4],
        "year": r[5], "volume": r[6], "issue": r[7], "pages": r[8], "bibtex_raw": r[9], "created_at": r[10]
    } for r in rows]

# ── Gestión de Roles y Acreditación Institucional ──

def get_user_role(orcid: str) -> Dict[str, Any]:
    """Obtiene el rol y permisos de un usuario según su ORCID."""
    if not orcid:
        return {"role": "guest", "status": "none"}
    clean_orc = str(orcid).strip().split('/')[-1]
    
    # Comprobar superadmin por variable de entorno
    admin_env = os.getenv("admins", "")
    admin_orcids = [o.strip().replace('https://orcid.org/', '').replace('http://orcid.org/', '') for o in admin_env.split(",") if o.strip()]
    if clean_orc in admin_orcids:
        return {"role": "super_admin", "status": "active", "institution": "GLOBAL"}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT role, status, institution, dependency FROM user_roles WHERE orcid = ?", (clean_orc,))
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "role": row[0],
            "status": row[1],
            "institution": row[2],
            "dependency": row[3]
        }
    return {"role": "researcher", "status": "active"}

def request_institutional_role(orcid: str, name: str, email: str, institution: str, dependency: str) -> bool:
    """Crea una solicitud de acreditación institucional (estado: PENDING)."""
    if not orcid or not email or not institution:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR REPLACE INTO user_roles (orcid, name, email, institution, dependency, role, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'institutional_admin', 'pending', CURRENT_TIMESTAMP)
        """, (clean_orc, name, email, institution, dependency))
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error solicitando rol institucional: {e}")
        return False
    finally:
        conn.close()

def approve_institutional_role(orcid: str, approved_by: str) -> bool:
    """Aprueba una solicitud de administrador institucional (acción realizada por super-admin)."""
    if not orcid:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE user_roles 
            SET status = 'active', approved_by = ?, approved_at = CURRENT_TIMESTAMP
            WHERE orcid = ?
        """, (approved_by, clean_orc))
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error aprobando rol: {e}")
        return False
    finally:
        conn.close()

def list_pending_role_requests() -> List[Dict[str, Any]]:
    """Lista solicitudes pendientes de acreditación institucional para el super-admin."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT orcid, name, email, institution, dependency, created_at FROM user_roles WHERE status = 'pending'")
    rows = cur.fetchall()
    conn.close()
    return [{
        "orcid": r[0], "name": r[1], "email": r[2], "institution": r[3], "dependency": r[4], "created_at": r[5]
    } for r in rows]

# ── Almacenamiento Encriptado de Tokens ORCID ──

def store_user_token(orcid: str, access_token: str, scope: str = "", expires_in: Optional[int] = None) -> bool:
    """Almacena un token de ORCID cifrado con Fernet."""
    if not orcid or not access_token:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    encrypted = encrypt_token(access_token)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR REPLACE INTO user_tokens (orcid, encrypted_token, scope, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (clean_orc, encrypted, scope))
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error guardando token cifrado: {e}")
        return False
    finally:
        conn.close()

def get_user_token(orcid: str, scope: Optional[str] = None) -> Optional[str]:
    """Recupera y descifra el token OAuth del usuario."""
    if not orcid:
        return None
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if scope:
        cur.execute("SELECT encrypted_token FROM user_tokens WHERE orcid = ? AND scope = ?", (clean_orc, scope))
    else:
        cur.execute("SELECT encrypted_token FROM user_tokens WHERE orcid = ? ORDER BY updated_at DESC LIMIT 1", (clean_orc,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return decrypt_token(row[0])
    return None


def reject_institutional_role(orcid: str, decided_by: str = "super_admin") -> bool:
    """Rechaza una solicitud de acreditación institucional."""
    if not orcid:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE user_roles 
            SET status = 'rejected', approved_by = ?, approved_at = CURRENT_TIMESTAMP
            WHERE orcid = ? AND status = 'pending'
        """, (decided_by, clean_orc))
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error rechazando rol institucional: {e}")
        return False
    finally:
        conn.close()


def list_active_institutional_admins() -> List[Dict[str, Any]]:
    """Lista todos los administradores institucionales aprobados y activos."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT orcid, name, email, institution, dependency, approved_by, approved_at 
        FROM user_roles 
        WHERE role = 'institutional_admin' AND status = 'active'
    """)
    rows = cur.fetchall()
    conn.close()
    return [{
        "orcid": r[0], "name": r[1], "email": r[2], "institution": r[3],
        "dependency": r[4], "approved_by": r[5], "approved_at": r[6]
    } for r in rows]


def is_user_institutional_admin(orcid: str, institution: Optional[str] = None) -> bool:
    """Verifica si un usuario cuenta con rol activo de administrador institucional."""
    if not orcid:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if institution:
        cur.execute(
            "SELECT 1 FROM user_roles WHERE orcid = ? AND role = 'institutional_admin' AND status = 'active' AND institution = ?",
            (clean_orc, institution)
        )
    else:
        cur.execute(
            "SELECT 1 FROM user_roles WHERE orcid = ? AND (role = 'institutional_admin' OR role = 'super_admin') AND status = 'active'",
            (clean_orc,)
        )
    row = cur.fetchone()
    conn.close()
    return bool(row)


def list_disclaimed_works(orcid: str) -> List[Dict[str, Any]]:
    """Devuelve la lista detallada de obras desmentidas por el autor."""
    if not orcid:
        return []
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT work_id, title, reason, disclaimed_at FROM user_disclaimed_works WHERE orcid = ? ORDER BY disclaimed_at DESC", (clean_orc,))
    rows = cur.fetchall()
    conn.close()
    return [{"work_id": r[0], "title": r[1], "reason": r[2], "created_at": r[3]} for r in rows]


def list_custom_works(orcid: str) -> List[Dict[str, Any]]:
    """Devuelve las obras cargadas manualmente por el usuario."""
    return get_custom_works(orcid)


def add_institutional_alias(canonical_entity: str, alias: str, created_by: str = "") -> bool:
    """Registra una variante de nombre para una institución."""
    if not canonical_entity or not alias:
        return False
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT OR IGNORE INTO institutional_aliases (canonical_entity, alias, created_by) VALUES (?, ?, ?)",
            (canonical_entity.strip(), alias.strip(), created_by)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error agregando alias institucional: {e}")
        return False
    finally:
        conn.close()


def get_institutional_aliases(canonical_entity: Optional[str] = None) -> List[Dict[str, Any]]:
    """Obtiene los alias institucionales registrados."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if canonical_entity:
        cur.execute("SELECT canonical_entity, alias, created_by, created_at FROM institutional_aliases WHERE canonical_entity = ?", (canonical_entity,))
    else:
        cur.execute("SELECT canonical_entity, alias, created_by, created_at FROM institutional_aliases ORDER BY canonical_entity, alias")
    rows = cur.fetchall()
    conn.close()
    return [{"canonical_entity": r[0], "alias": r[1], "created_by": r[2], "created_at": r[3]} for r in rows]


def import_bibtex_file(orcid: str, bibtex_content: str) -> tuple:
    """
    Parsea e importa obras desde un archivo .bib subido por el autor.
    Retorna (num_obras_importadas, mensaje).
    """
    if not orcid or not bibtex_content:
        return 0, "Contenido o identificador vacío."
    
    clean_orc = str(orcid).strip().split('/')[-1]
    
    # Parser regex robusto de BibTeX
    entry_pattern = re.compile(r'@(\w+)\s*\{\s*([^,]+),([^@]*)\}', re.DOTALL)
    imported = 0

    for match in entry_pattern.finditer(bibtex_content):
        entry_type = match.group(1).lower()
        if entry_type in ["comment", "string", "preamble"]:
            continue
        key = match.group(2).strip()
        body = match.group(3)

        fields = {}
        for line in body.split('\n'):
            line = line.strip()
            if '=' in line:
                parts = line.split('=', 1)
                k = parts[0].strip().lower()
                v = parts[1].strip().rstrip(',').strip('{}""\'')
                fields[k] = v

        title = fields.get("title") or key
        authors = fields.get("author") or fields.get("authors") or ""
        journal = fields.get("journal") or fields.get("booktitle") or ""
        year_str = fields.get("year")
        year = int(year_str) if year_str and year_str.isdigit() else None
        doi = fields.get("doi") or ""
        volume = fields.get("volume") or ""
        number = fields.get("number") or ""
        pages = fields.get("pages") or ""

        ok = add_custom_work(
            orcid=clean_orc,
            title=title,
            authors=authors,
            journal=journal,
            year=year,
            doi=doi,
            volume=volume,
            issue=number,
            pages=pages,
            bibtex_raw=match.group(0)
        )
        if ok:
            imported += 1

    return imported, f"Se importaron con éxito {imported} publicaciones a tu colección personal."


# ── Funciones de Privacidad y Ocultamiento de Perfiles (Derechos ARCO) ──

def hide_profile(orcid: str, academic_id: Optional[str] = None, academic_name: Optional[str] = None, reason: str = "Ocultado por el autor en Mi Espacio") -> bool:
    """Registra un perfil como oculto del directorio público."""
    if not orcid:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT OR REPLACE INTO hidden_profiles (orcid, academic_id, academic_name, hidden_at, reason)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)""",
            (clean_orc, (academic_id or "").strip(), (academic_name or "").strip(), reason)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error en hide_profile: {e}")
        return False
    finally:
        conn.close()

def unhide_profile(orcid: str) -> bool:
    """Reactiva la visibilidad pública de un perfil previamente oculto."""
    if not orcid:
        return False
    clean_orc = str(orcid).strip().split('/')[-1]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM hidden_profiles WHERE orcid = ?", (clean_orc,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[curation_service] Error en unhide_profile: {e}")
        return False
    finally:
        conn.close()

def is_profile_hidden(orcid: Optional[str] = None, name: Optional[str] = None, academic_id: Optional[str] = None) -> bool:
    """Determina si un investigador está marcado como oculto."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        if orcid:
            clean_orc = str(orcid).strip().split('/')[-1]
            cur.execute("SELECT 1 FROM hidden_profiles WHERE orcid = ? LIMIT 1", (clean_orc,))
            if cur.fetchone():
                return True
        if academic_id:
            clean_id = str(academic_id).strip()
            cur.execute("SELECT 1 FROM hidden_profiles WHERE academic_id = ? OR orcid = ? LIMIT 1", (clean_id, clean_id))
            if cur.fetchone():
                return True
        if name:
            clean_name = str(name).strip().lower()
            norm_q = " ".join(clean_name.replace(",", "").split())
            cur.execute("SELECT academic_name FROM hidden_profiles WHERE academic_name IS NOT NULL AND academic_name != ''")
            for row in cur.fetchall():
                h_name = (row[0] or "").strip().lower()
                norm_h = " ".join(h_name.replace(",", "").split())
                if norm_h and (norm_h == norm_q or norm_h in norm_q or norm_q in norm_h):
                    return True
        return False
    except Exception as e:
        print(f"[curation_service] Error en is_profile_hidden: {e}")
        return False
    finally:
        conn.close()

def get_hidden_identities() -> Dict[str, Any]:
    """Retorna los conjuntos de orcids, ids y nombres normalizados de perfiles ocultos."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    hidden_orcids = set()
    hidden_ids = set()
    hidden_names = set()
    try:
        cur.execute("SELECT orcid, academic_id, academic_name FROM hidden_profiles")
        for orcid, aid, aname in cur.fetchall():
            if orcid:
                clean_o = str(orcid).strip().split('/')[-1].lower()
                hidden_orcids.add(clean_o)
                hidden_orcids.add(f"https://orcid.org/{clean_o}")
            if aid:
                hidden_ids.add(str(aid).strip().lower())
            if aname:
                norm_name = " ".join(str(aname).replace(",", "").strip().lower().split())
                hidden_names.add(norm_name)
                hidden_names.add(str(aname).strip().lower())
    except Exception as e:
        print(f"[curation_service] Error en get_hidden_identities: {e}")
    finally:
        conn.close()
    return {
        "orcids": hidden_orcids,
        "ids": hidden_ids,
        "names": hidden_names
    }


class CurationService:
    """Clase singleton para orquestar la curación en la UI."""
    def claim_work(self, orcid: str, work_id: str, title: str = "") -> bool:
        return claim_work(orcid, work_id)
        
    def disclaim_work(self, orcid: str, work_id: str, title: str = "", reason: str = "") -> bool:
        return disclaim_work(orcid, work_id, reason=reason)
        
    def list_disclaimed_works(self, orcid: str) -> List[Dict[str, Any]]:
        return list_disclaimed_works(orcid)
        
    def list_custom_works(self, orcid: str) -> List[Dict[str, Any]]:
        return list_custom_works(orcid)
        
    def import_bibtex_file(self, orcid: str, bibtex_content: str) -> tuple:
        return import_bibtex_file(orcid, bibtex_content)
        
    def store_user_token(self, user_orcid: str, access_token: str, scope: str = "", client_id: Optional[str] = None) -> bool:
        return store_user_token(user_orcid, access_token, scope=scope)
        
    def get_user_token(self, user_orcid: str, scope: Optional[str] = None) -> Optional[str]:
        return get_user_token(user_orcid, scope=scope)
        
    def request_accreditation(self, user_orcid: str, user_name: str, institution_name: str, institutional_email: str, position: str, notes: str = "") -> tuple:
        ok = request_institutional_role(user_orcid, user_name, institutional_email, institution_name, position)
        if ok:
            return True, "Solicitud enviada exitosamente. El administrador la revisará a la brevedad."
        return False, "Ya existe una solicitud pendiente o ocurrió un error al registrarla."
        
    def list_pending_accreditations(self) -> List[Dict[str, Any]]:
        return list_pending_role_requests()
        
    def decide_accreditation(self, user_orcid: str, decision: str, decided_by: str = "super_admin") -> bool:
        if decision.upper() == "APPROVE":
            return approve_institutional_role(user_orcid, decided_by)
        else:
            return reject_institutional_role(user_orcid, decided_by)
            
    def list_active_institutional_admins(self) -> List[Dict[str, Any]]:
        return list_active_institutional_admins()
        
    def get_user_roles(self, orcid: str) -> Dict[str, Any]:
        return get_user_role(orcid)
        
    def is_user_institutional_admin(self, orcid: str, institution_name: Optional[str] = None) -> bool:
        return is_user_institutional_admin(orcid, institution_name)
        
    def get_institutional_aliases(self, institution_name: Optional[str] = None) -> List[Dict[str, Any]]:
        return get_institutional_aliases(institution_name)
        
    def add_institutional_alias(self, institution_name: str, alias: str, created_by: str = "") -> bool:
        return add_institutional_alias(institution_name, alias, created_by)

    def hide_profile(self, orcid: str, academic_id: Optional[str] = None, academic_name: Optional[str] = None, reason: str = "Ocultado por el autor en Mi Espacio") -> bool:
        return hide_profile(orcid, academic_id=academic_id, academic_name=academic_name, reason=reason)

    def unhide_profile(self, orcid: str) -> bool:
        return unhide_profile(orcid)

    def is_profile_hidden(self, orcid: Optional[str] = None, name: Optional[str] = None, academic_id: Optional[str] = None) -> bool:
        return is_profile_hidden(orcid=orcid, name=name, academic_id=academic_id)

    def get_hidden_identities(self) -> Dict[str, Any]:
        return get_hidden_identities()


_service_instance = CurationService()

def get_curation_service() -> CurationService:
    return _service_instance

