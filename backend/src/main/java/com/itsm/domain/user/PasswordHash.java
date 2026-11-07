package com.itsm.domain.user;

import com.itsm.domain.exception.ValidationException;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * A salted PBKDF2 password hash. Plain-text passwords are never stored.
 * Immutable; serialises to a single string ("salt:hash", Base64) for the database.
 */
public final class PasswordHash {
    private static final int ITERATIONS = 65_536;
    private static final SecureRandom RANDOM = new SecureRandom();

    private final byte[] salt;
    private final byte[] hash;

    private PasswordHash(byte[] salt, byte[] hash) {
        this.salt = salt.clone();
        this.hash = hash.clone();
    }

    /** Validates strength, then hashes with a fresh random salt. */
    public static PasswordHash of(String password) {
        validateStrength(password);
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        return new PasswordHash(salt, derive(password, salt));
    }

    /** Rebuild from the string produced by {@link #encode()} (Member 3: read from the DB). */
    public static PasswordHash decode(String encoded) {
        String[] parts = encoded == null ? new String[0] : encoded.split(":");
        if (parts.length != 2) throw new ValidationException("Malformed stored password hash.");
        Base64.Decoder d = Base64.getDecoder();
        return new PasswordHash(d.decode(parts[0]), d.decode(parts[1]));
    }

    /** "salt:hash" in Base64 — safe to store in a VARCHAR column. */
    public String encode() {
        Base64.Encoder e = Base64.getEncoder();
        return e.encodeToString(salt) + ":" + e.encodeToString(hash);
    }

    /** Constant-time comparison so response timing doesn't leak information. */
    public boolean matches(String password) {
        return MessageDigest.isEqual(derive(password, salt), hash);
    }

    static void validateStrength(String password) {
        if (password == null || password.length() < 8
                || password.chars().noneMatch(Character::isDigit)
                || password.chars().noneMatch(Character::isLetter)) {
            throw new ValidationException("Password must be 8+ characters with letters and digits.");
        }
    }

    private static byte[] derive(String password, byte[] salt) {
        try {
            PBEKeySpec spec = new PBEKeySpec((password == null ? "" : password).toCharArray(), salt, ITERATIONS, 256);
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Password hashing unavailable", e);
        }
    }

    @Override public String toString() { return "PasswordHash[****]"; }
}
