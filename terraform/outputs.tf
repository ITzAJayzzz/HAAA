output "public_ip" {
  description = "Public IP of the GlobalTalk server"
  value       = aws_eip.app.public_ip
}

output "public_dns" {
  description = "Public DNS of the GlobalTalk server"
  value       = aws_instance.app.public_dns
}

output "ssh_command" {
  description = "SSH into the server"
  value       = "ssh ubuntu@${aws_eip.app.public_ip}"
}

output "app_url" {
  description = "Application URL"
  value       = "http://${aws_eip.app.public_ip}"
}
