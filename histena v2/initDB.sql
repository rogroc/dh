
CREATE TABLE IF NOT EXISTS "works" (
	"ID"	INTEGER NOT NULL,
	"title"	TEXT,
	"description"	TEXT,
	"abbreviation"	TEXT,
	PRIMARY KEY("ID" AUTOINCREMENT)
);

CREATE TABLE IF NOT EXISTS "persons" (
	"ID"	INTEGER NOT NULL,
	"name"	TEXT,
	"info"	TEXT,
	PRIMARY KEY("ID" AUTOINCREMENT)
);

CREATE TABLE IF NOT EXISTS "keywords" (
	"ID"	INTEGER NOT NULL,
	"name"	TEXT,
	"description"	TEXT,
	PRIMARY KEY("ID" AUTOINCREMENT)
);

CREATE TABLE IF NOT EXISTS "locations" (
	"ID"	INTEGER NOT NULL,
	"geonameId"	INTEGER,
	"name"	TEXT,
	"alternate"	TEXT,
	"lat"	REAL,
	"long"	REAL,
	"class"	TEXT,
	"code"	TEXT,
	"country"	TEXT,
	PRIMARY KEY("ID" AUTOINCREMENT)
);

CREATE TABLE IF NOT EXISTS "docs" (
	"ID"	INTEGER NOT NULL,
	"id_work"	INTEGER,
	"title"	TEXT,
	"date"	TEXT,
	"text"	TEXT,
	"ref"	TEXT,
	"id_location"	INTEGER,
	"id_author"	INTEGER,
	PRIMARY KEY("ID" AUTOINCREMENT)
);

CREATE TABLE IF NOT EXISTS "annotations" (
	"ID"	INTEGER NOT NULL,
	"type"	TEXT,
	"begin"	TEXT,
	"end"	TEXT,
	"id_doc"	INTEGER,
	PRIMARY KEY("ID" AUTOINCREMENT)
);

CREATE TABLE IF NOT EXISTS "annotationPerson" (
	"id_annotation"	INTEGER,
	"id_person"	INTEGER
);

CREATE TABLE IF NOT EXISTS "annotationLocation" (
	"id_annotation"	INTEGER,
	"id_location"	INTEGER
);

CREATE TABLE IF NOT EXISTS "annotationKeyword" (
	"id_annotation"	INTEGER,
	"id_keyword"	INTEGER
);
