package com.itsm.domain.exception;

public class CategoryNotFoundException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public CategoryNotFoundException(String message) { super("CATEGORY_NOT_FOUND", message); }
    @Override public int httpStatus() { return 404; }
}
