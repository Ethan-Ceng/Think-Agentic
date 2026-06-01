-- ----------------------------
-- Table structure for la_file
-- ----------------------------
DROP TABLE IF EXISTS "la_file";
CREATE TABLE "la_file"  (
  "id" BIGSERIAL,
  "cid" INTEGER NOT NULL DEFAULT 0,
  "aid" INTEGER NOT NULL DEFAULT 0,
  "uid" INTEGER NOT NULL DEFAULT 0,
  "type" SMALLINT NOT NULL DEFAULT 10,
  "name" varchar(100) NOT NULL DEFAULT '',
  "uri" varchar(200) NOT NULL,
  "ext" varchar(10) NOT NULL DEFAULT '',
  "size" INTEGER NOT NULL DEFAULT 0,
  "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "deleted_at" TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX "idx_file_cid" ON "la_file"("cid");
CREATE INDEX "idx_file_deleted_at" ON "la_file"("deleted_at");

-- ----------------------------
-- Records of la_file
-- ----------------------------

-- ----------------------------
-- Table structure for la_file_folder
-- ----------------------------
DROP TABLE IF EXISTS "la_file_folder";
CREATE TABLE "la_file_folder"  (
  "id" SERIAL,
  "pid" INTEGER NOT NULL DEFAULT 0,
  "type" SMALLINT NOT NULL DEFAULT 10,
  "name" varchar(32) NOT NULL DEFAULT '',
  "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "deleted_at" TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY ("id")
);
CREATE INDEX "idx_file_folder_deleted_at" ON "la_file_folder"("deleted_at");