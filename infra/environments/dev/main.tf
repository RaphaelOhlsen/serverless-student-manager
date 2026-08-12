module "student_store" {
  source = "../../modules/student_store"

  table_name = "serverless-student-manager-dev-students"

  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false
}
