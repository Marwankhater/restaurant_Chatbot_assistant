# Action server: the custom actions and the booking domain, without the full Rasa stack.
FROM rasa/rasa-sdk:3.6.2
WORKDIR /app
USER root
COPY requirements-actions.txt ./
RUN pip install --no-cache-dir -r requirements-actions.txt
COPY restaurant ./restaurant
COPY actions ./actions
RUN mkdir -p /data && chown 1001 /data
USER 1001
ENV RESTAURANT_DB=/data/restaurant.db
EXPOSE 5055
CMD ["start", "--actions", "actions"]
