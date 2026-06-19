from rest_framework import serializers
from apps.crm.models import Lead, Tag, LeadActivity

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name')
        read_only_fields = ('id',)

class LeadActivitySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = LeadActivity
        fields = ('id', 'lead', 'user', 'username', 'activity_type', 'description', 'created_at')
        read_only_fields = ('id', 'created_at')

from apps.crm.models import Lead, Tag, LeadActivity, LeadCollection

class LeadCollectionSerializer(serializers.ModelSerializer):
    leads_count = serializers.IntegerField(source='leads.count', read_only=True)

    class Meta:
        model = LeadCollection
        fields = '__all__'
        read_only_fields = ('id', 'business', 'created_at', 'updated_at')

class LeadSerializer(serializers.ModelSerializer):
    tags_detail = TagSerializer(source='tags', many=True, read_only=True)
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, required=False)
    collection_name = serializers.CharField(source='collection.name', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ('id', 'business', 'created_at', 'updated_at')

    def __init__(self, *args, **kwargs):
        # Dynamically filter choice fields to only show items belonging to the active business
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'business'):
            self.fields['tags'].child_relation.queryset = Tag.objects.filter(business=request.business)
            if 'collection' in self.fields:
                self.fields['collection'].queryset = LeadCollection.objects.filter(business=request.business)
