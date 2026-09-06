data "aws_region" "current" {}

locals {
  region                   = var.aws_region == null ? data.aws_region.current.name : var.aws_region
  container_name           = "${var.name_prefix}-backend-api"
  migration_container_name = "${var.name_prefix}-db-migration"

  # The DB secret ARN is non-sensitive configuration: the application fetches
  # the secret at runtime through its task role. The bearer token is different:
  # ECS injects its value through the secrets block using the execution role.
  container_definitions = [
    {
      name      = local.container_name
      image     = var.container_image
      essential = true

      portMappings = [
        {
          containerPort = var.app_port
          hostPort      = var.app_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "BACKEND_DB_SECRET_ARN"
          value = var.backend_db_secret_arn
        },
        {
          name  = "BACKEND_DB_NAME"
          value = var.backend_db_name
        },
      ]

      secrets = [
        {
          name      = "BACKEND_INTERNAL_BEARER_TOKEN"
          valueFrom = var.backend_bearer_secret_arn
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.this.name
          "awslogs-region"        = local.region
          "awslogs-stream-prefix" = "backend-api"
        }
      }
    }
  ]

  migration_container_definitions = [
    {
      name      = local.migration_container_name
      image     = var.migration_container_image
      essential = true

      environment = [
        {
          name  = "BACKEND_DB_SECRET_ARN"
          value = var.backend_db_secret_arn
        },
        {
          name  = "BACKEND_DB_NAME"
          value = var.backend_db_name
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.migration.name
          "awslogs-region"        = local.region
          "awslogs-stream-prefix" = "db-migration"
        }
      }
    }
  ]
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.name_prefix}-backend-api"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-backend-api-logs"
    Tier = "private-app"
    Role = "ecs"
  })
}

resource "aws_cloudwatch_log_group" "migration" {
  name              = "/ecs/${var.name_prefix}-migration"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-migration-logs"
    Tier = "private-app"
    Role = "migration"
  })
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-cluster"
    Tier = "private-app"
    Role = "ecs"
  })
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name_prefix}-backend-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.ecs_task_cpu)
  memory                   = tostring(var.ecs_task_memory)
  execution_role_arn       = var.backend_execution_role_arn
  task_role_arn            = var.backend_task_role_arn

  container_definitions = jsonencode(local.container_definitions)

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-backend-api-task"
    Tier = "private-app"
    Role = "ecs"
  })
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.name_prefix}-db-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.migration_task_cpu)
  memory                   = tostring(var.migration_task_memory)
  execution_role_arn       = var.migration_execution_role_arn
  task_role_arn            = var.migration_task_role_arn

  container_definitions = jsonencode(local.migration_container_definitions)

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-db-migration-task"
    Tier = "private-app"
    Role = "migration"
  })
}

resource "aws_ecs_service" "this" {
  name            = "${var.name_prefix}-backend-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = local.container_name
    container_port   = var.app_port
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-backend-api"
    Tier = "private-app"
    Role = "ecs"
  })
}

# Autoscaling is designed in but disabled for the MVP. Both resources use
# count = var.enable_autoscaling ? 1 : 0 and enable_autoscaling defaults to
# false, so nothing is created and ecs_desired_count remains Terraform-owned.
resource "aws_appautoscaling_target" "this" {
  count = var.enable_autoscaling ? 1 : 0

  max_capacity       = var.autoscaling_max_capacity
  min_capacity       = var.autoscaling_min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  count = var.enable_autoscaling ? 1 : 0

  name               = "${var.name_prefix}-backend-api-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.this[0].resource_id
  scalable_dimension = aws_appautoscaling_target.this[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.this[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = var.autoscaling_cpu_target
  }
}
