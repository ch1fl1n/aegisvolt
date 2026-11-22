output "state_bucket" {
  description = "Bucket donde vive el estado de dev, test y prod"
  value       = aws_s3_bucket.tfstate.bucket
}

output "lock_table" {
  description = "Tabla de bloqueo de respaldo (plan B)"
  value       = aws_dynamodb_table.tflock.name
}
