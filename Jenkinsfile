pipeline {
    agent any

    environment {
        IMAGE_NAME     = 'openapi-mock'
        CONTAINER_NAME = 'openapi-mock'
        HOST_PORT      = '8090'
        // 게이트웨이에 배포된 명세를 담는 볼륨. 컨테이너를 지웠다 다시 띄워도 남아야 한다.
        DATA_VOLUME    = 'openapi-mock-data'
    }

    options {
        disableConcurrentBuilds()
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build image') {
            steps {
                sh """
                    docker build -t ${IMAGE_NAME}:${BUILD_NUMBER} -t ${IMAGE_NAME}:latest .
                """
            }
        }

        stage('Deploy') {
            steps {
                sh """
                    docker stop ${CONTAINER_NAME} || true
                    docker rm ${CONTAINER_NAME} || true
                    docker run -d \
                        --name ${CONTAINER_NAME} \
                        --restart unless-stopped \
                        -p ${HOST_PORT}:8090 \
                        -v ${DATA_VOLUME}:/data \
                        ${IMAGE_NAME}:${BUILD_NUMBER}
                """
            }
        }

        stage('Health check') {
            steps {
                sh """
                    for i in \$(seq 1 10); do
                        if curl -sf http://localhost:${HOST_PORT}/health; then
                            echo "healthy"
                            exit 0
                        fi
                        echo "waiting for container to become healthy... (\$i/10)"
                        sleep 3
                    done
                    echo "openapi-mock did not become healthy in time"
                    docker logs --tail 100 ${CONTAINER_NAME}
                    exit 1
                """
            }
        }
    }

    post {
        success {
            sh "docker image prune -f --filter 'label!=keep' --filter until=24h || true"
        }
        failure {
            echo 'Build/Deploy failed - see stage logs above (docker logs printed on health-check failure).'
        }
    }
}
