module "student_store" {
  source = "../../modules/student_store"

  table_name = "serverless-student-manager-dev-students"

  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false
}

module "user_store" {
  source = "../../modules/user_store"

  table_name = "serverless-student-manager-dev-users"

  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false
}

module "identity" {
  source = "../../modules/identity"

  user_pool_name        = "serverless-student-manager-dev-user-pool"
  user_pool_client_name = "serverless-student-manager-dev-web"
}
