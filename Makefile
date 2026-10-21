IMAGE_NAME := coat-cost-api
CONTAINER_NAME := coat-cost-api
AWS_PROFILE := modernisation-platform-developer

build:
	docker build -t $(IMAGE_NAME) .

run: build
	docker run --rm \
		-p 8000:8000 \
		-v ~/.aws:/home/appuser/.aws:ro \
		-e AWS_PROFILE=$(AWS_PROFILE) \
		-e APP_ENV=development \
		--name $(CONTAINER_NAME) \
		$(IMAGE_NAME)

stop:
	-docker stop $(CONTAINER_NAME)

shell:
	docker exec -it $(CONTAINER_NAME) /bin/sh

health:
	curl http://localhost:8000/health